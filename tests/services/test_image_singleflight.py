"""Artwork callers share in-flight work and can retry failed work."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from retrocheevos.services import image_service


class ImageSingleflightTests(unittest.TestCase):
    def test_concurrent_callers_share_result_and_failure_releases_entry(self):
        game = Mock(id=42)
        started, release, joined = Event(), Event(), Event()

        def load(_game):
            started.set()
            if not release.wait(3):
                raise AssertionError('test did not release owner')
            return Path('/tmp/cover.png')

        with patch.object(image_service, '_ensure_game_image_cached', side_effect=load) as fetch:
            with ThreadPoolExecutor(2) as pool:
                first = pool.submit(image_service.ensure_game_image_cached, game)
                self.assertTrue(started.wait(3))
                future = next(iter(image_service._game_image_flights.values()))
                real_result = future.result

                def result():
                    joined.set()
                    return real_result(timeout=3)

                with patch.object(future, 'result', side_effect=result):
                    second = pool.submit(image_service.ensure_game_image_cached, game)
                    try:
                        self.assertTrue(joined.wait(3))
                    finally:
                        release.set()
                    self.assertEqual(first.result(3), second.result(3))
                self.assertEqual(fetch.call_count, 1)
        self.assertFalse(image_service._game_image_flights)
        with patch.object(image_service, '_ensure_game_image_cached', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                image_service.ensure_game_image_cached(game)
        self.assertFalse(image_service._game_image_flights)
        with patch.object(image_service, '_ensure_game_image_cached', return_value=Path('/tmp/recovered.png')):
            self.assertEqual(image_service.ensure_game_image_cached(game), Path('/tmp/recovered.png'))
