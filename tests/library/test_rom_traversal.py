"""Traversal starts immediately, prunes only established exclusions and closes handles."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrocheevos.library import rom_traversal
from retrocheevos.services.library_service import SKIPPED_DIR_NAMES
from retrocheevos.utils.cancellation import OperationCancelled


class StreamingEntries:
    def __init__(self, size):
        self.size = size
        self.pulled = 0
        self.closed = False

    def __next__(self):
        if self.pulled >= self.size:
            raise StopIteration
        self.pulled += 1
        return SimpleNamespace(
            path=f'/roms/game{self.pulled}.nes', name=f'game{self.pulled}.nes',
            is_dir=lambda follow_symlinks=False: False, is_file=lambda: True,
        )

    def close(self):
        self.closed = True


class RomTraversalTests(unittest.TestCase):
    def test_first_file_is_yielded_without_enumerating_remaining_tree(self):
        entries = StreamingEntries(100000)
        progress = []
        with patch.object(rom_traversal.os, 'scandir', return_value=entries):
            files = rom_traversal.iter_rom_files(Path('/roms'), SKIPPED_DIR_NAMES,
                                                lambda *args: progress.append(args))
            self.assertEqual(next(files), Path('/roms/game1.nes'))
            self.assertEqual(entries.pulled, 1)
            self.assertEqual(progress[0], (0, '/roms'))
            self.assertEqual(progress[-1], (1, '/roms/game1.nes'))
            files.close()
        self.assertTrue(entries.closed)

    def test_pruning_preserves_hidden_directories_and_all_file_formats(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for name in ('Images', 'BIOS', '.private', 'nested'):
                (root / name).mkdir()
                (root / name / 'game.rvz').touch()
            for suffix in ('nes', 'gba', 'nds', 'zip', 'chd', 'iso', 'cue', 'bin', 'rvz'):
                (root / f'game.{suffix}').touch()
            actual_scandir = rom_traversal.os.scandir
            opened = []

            def scandir(path):
                opened.append(Path(path))
                return actual_scandir(path)

            with patch.object(rom_traversal.os, 'scandir', side_effect=scandir):
                files = set(rom_traversal.iter_rom_files(root, SKIPPED_DIR_NAMES))
            self.assertNotIn(root / 'Images', opened)
            self.assertNotIn(root / 'BIOS', opened)
            self.assertIn(root / '.private/game.rvz', files)
            self.assertIn(root / 'nested/game.rvz', files)
            self.assertEqual(len(files), 11)

    def test_cancellation_during_discovery_closes_directory_before_hashing(self):
        entries = StreamingEntries(100000)
        cancelled = False

        def progress(count, _path):
            nonlocal cancelled
            cancelled = count > 0

        with patch.object(rom_traversal.os, 'scandir', return_value=entries):
            with self.assertRaises(OperationCancelled):
                list(rom_traversal.iter_rom_files(Path('/roms'), SKIPPED_DIR_NAMES,
                                                progress, lambda: cancelled))
        self.assertTrue(entries.closed)
        self.assertEqual(entries.pulled, 1)

    def test_unreadable_subdirectory_reports_error_and_keeps_siblings(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'blocked').mkdir()
            (root / 'game.nes').touch()
            real_scandir = rom_traversal.os.scandir
            errors = []

            def scandir(path):
                if Path(path).name == 'blocked':
                    raise PermissionError('unreadable')
                return real_scandir(path)

            with patch.object(rom_traversal.os, 'scandir', side_effect=scandir):
                files = list(rom_traversal.iter_rom_files(
                    root, SKIPPED_DIR_NAMES, on_error=lambda *args: errors.append(args),
                ))
            self.assertEqual(files, [root / 'game.nes'])
            self.assertEqual(errors[0][0], root / 'blocked')

    def test_directory_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'game.nes').touch()
            try:
                (root / 'cycle').symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('Directory symlinks are unavailable')
            self.assertEqual(list(rom_traversal.iter_rom_files(root, SKIPPED_DIR_NAMES)), [root / 'game.nes'])
