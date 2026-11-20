"""Shared artwork files are published atomically and failed writes are cleaned."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from retrocheevos.library import game_images


class AtomicImageTests(unittest.TestCase):
    def test_windows_sharing_violation_retries_atomic_publication(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'cover.png'
            target.write_bytes(b'old')
            replace = game_images.os.replace
            busy = PermissionError('temporarily in use')
            busy.winerror = 32
            attempts = 0

            def publish(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    self.assertEqual(target.read_bytes(), b'old')
                    raise busy
                replace(source, destination)

            with patch.object(game_images.requests, 'get', return_value=Mock(content=b'new')), \
                 patch.object(game_images.sys, 'platform', 'win32'), \
                 patch.object(game_images.os, 'replace', side_effect=publish), \
                 patch.object(game_images.time, 'sleep'):
                game_images.download_image('https://example.test/cover', target)
            self.assertEqual(attempts, 2)
            self.assertEqual(target.read_bytes(), b'new')
            self.assertEqual(list(Path(root).iterdir()), [target])

    def test_windows_persistent_access_denied_is_bounded_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'cover.png'
            target.write_bytes(b'old')
            denied = PermissionError('access denied')
            denied.winerror = 5
            with patch.object(game_images.requests, 'get', return_value=Mock(content=b'new')), \
                 patch.object(game_images.sys, 'platform', 'win32'), \
                 patch.object(game_images.os, 'replace', side_effect=denied) as publish, \
                 patch.object(game_images.time, 'sleep'):
                with self.assertRaises(PermissionError):
                    game_images.download_image('https://example.test/cover', target)
            self.assertEqual(publish.call_count, 5)
            self.assertEqual(target.read_bytes(), b'old')
            self.assertEqual(list(Path(root).iterdir()), [target])

    def test_failed_replace_preserves_existing_file_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'cover.png'
            target.write_bytes(b'old')
            with patch.object(game_images.requests, 'get', return_value=Mock(content=b'new')):
                with patch.object(game_images.os, 'replace', side_effect=OSError('interrupted')):
                    with self.assertRaises(OSError):
                        game_images.download_image('https://example.test/cover', target)
            self.assertEqual(target.read_bytes(), b'old')
            self.assertEqual(list(Path(root).iterdir()), [target])

    def test_concurrent_writes_publish_whole_files(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'cover.png'
            with patch.object(game_images.requests, 'get', return_value=Mock(content=b'x' * 100000)):
                with ThreadPoolExecutor(4) as pool:
                    list(pool.map(lambda _: game_images.download_image('https://example.test/cover', target), range(8)))
            self.assertEqual(target.read_bytes(), b'x' * 100000)
            self.assertEqual(list(Path(root).iterdir()), [target])
