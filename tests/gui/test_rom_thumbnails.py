"""Library covers for unmatched ROMs: real asynchronous artwork, manual choices win."""

import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from retrocheevos.gui import image_loader
from retrocheevos.gui.models import library_grid_model
from retrocheevos.gui.models.library_grid_model import FallbackRole, LibraryGridModel
from retrocheevos.models.library import InstalledRom, LibraryEntry

_app = QApplication.instance() or QApplication([])
DECORATION = Qt.ItemDataRole.DecorationRole


def wait_until(predicate) -> None:
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('Thumbnail load timed out')
        QTest.qWait(5)


def center_color(pixmap):
    image = pixmap.toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2)


class RomThumbnailTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.art = self.root / 'cover.png'
        self.manual = self.root / 'manual.png'
        Image.new('RGB', (32, 48), 'red').save(self.art)
        patcher = patch.object(library_grid_model, 'cached_local_cover_path', return_value=self.manual)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rom = InstalledRom('/roms/game.rvz', '', 19, id=7)
        self.loader = image_loader.ImageLoader()
        self.addCleanup(self.loader.shutdown)
        self.model = LibraryGridModel(self.loader)
        self.model.set_entries(
            [LibraryEntry('rom', 'game', 19, [self.rom.file_path], rom=self.rom)], {19: 'Wii'}
        )
        self.index = self.model.index(0)

    def test_unmatched_rvz_loads_art_without_a_catalog_guess(self) -> None:
        game_results = []
        self.loader.image_ready.connect(lambda *args: game_results.append(args))
        with patch.object(image_loader, 'ensure_rom_image_cached', return_value=self.art) as load:
            self.assertIsNone(self.index.data(DECORATION))
            wait_until(lambda: self.index.data(DECORATION) is not None)
        load.assert_called_once_with(self.rom, None)
        color = center_color(self.index.data(DECORATION))
        self.assertGreater(color.red(), 200)
        self.assertLess(color.blue(), 30)
        self.assertEqual(game_results, [])

    def test_pending_request_is_deduplicated_and_manual_cover_wins(self) -> None:
        release, started = Event(), Event()

        def load(*_args):
            started.set()
            release.wait(2)
            return self.art

        with patch.object(image_loader, 'ensure_rom_image_cached', side_effect=load) as load_image:
            try:
                self.index.data(DECORATION)
                wait_until(started.is_set)
                self.index.data(DECORATION)
                self.loader.request_rom(self.rom)
                self.assertEqual(load_image.call_count, 1)
                Image.new('RGB', (40, 40), 'blue').save(self.manual)
                self.model.forget_cover(('rom', 7))
                self.assertGreater(center_color(self.index.data(DECORATION)).blue(), 200)
            finally:
                release.set()
                wait_until(lambda: not self.loader._rom_pending)
        QTest.qWait(10)
        color = center_color(self.index.data(DECORATION))
        self.assertGreater(color.blue(), 200)
        self.assertLess(color.red(), 30)

    def test_missing_art_falls_back_to_the_console_name(self) -> None:
        with patch.object(image_loader, 'ensure_rom_image_cached', return_value=None):
            self.assertIsNone(self.index.data(DECORATION))
            wait_until(lambda: not self.loader._rom_pending)
        self.assertIsNone(self.index.data(DECORATION))
        self.assertEqual(self.index.data(FallbackRole), 'Wii')


if __name__ == '__main__':
    unittest.main()
