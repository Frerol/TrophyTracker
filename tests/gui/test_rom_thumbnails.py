"""Unmatched ROMs receive real asynchronous artwork and retain manual choices."""

import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from retrocheevos.gui import image_loader
from retrocheevos.models.library import InstalledRom
from retrocheevos.widgets import unmatched_rom_card

_app = QApplication.instance() or QApplication([])


def wait_until(predicate) -> None:
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('Thumbnail load timed out')
        QTest.qWait(5)


class RomThumbnailTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.art = self.root / 'cover.png'
        self.manual = self.root / 'manual.png'
        Image.new('RGB', (32, 48), 'red').save(self.art)
        patcher = patch.object(unmatched_rom_card, 'cached_local_cover_path', return_value=self.manual)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rom = InstalledRom('/roms/game.rvz', '', 19, id=7)
        self.loader = image_loader.ImageLoader()

    def test_unmatched_rvz_loads_art_without_a_catalog_guess(self) -> None:
        received = []
        game_results = []
        self.loader.rom_image_ready.connect(lambda key, pixmap: received.append((key, pixmap)))
        self.loader.image_ready.connect(lambda *args: game_results.append(args))
        with patch.object(image_loader, 'ensure_rom_image_cached', return_value=self.art):
            card = unmatched_rom_card.UnmatchedRomCard(self.rom, 'Wii', image_loader=self.loader, cover_size=100)
            try:
                wait_until(lambda: received and not self.loader._rom_pending)
                self.assertEqual(received[0][0], 7)
                self.assertFalse(received[0][1].isNull())
                color = card._cover_button.icon().pixmap(100, 100).toImage().pixelColor(50, 50)
                self.assertGreater(color.red(), 200)
                self.assertLess(color.blue(), 30)
                self.assertEqual(game_results, [])
            finally:
                card.close()

    def test_pending_request_is_deduplicated_and_manual_cover_wins(self) -> None:
        release = Event()
        started = Event()
        def load(*_args):
            started.set()
            release.wait(2)
            return self.art
        with patch.object(image_loader, 'ensure_rom_image_cached', side_effect=load) as load_image:
            card = unmatched_rom_card.UnmatchedRomCard(self.rom, 'Wii', image_loader=self.loader, cover_size=100)
            try:
                wait_until(started.is_set)
                self.loader.request_rom(self.rom)
                self.assertEqual(load_image.call_count, 1)
                Image.new('RGB', (40, 40), 'blue').save(self.manual)
                card._refresh_cover()
                release.set()
                wait_until(lambda: not self.loader._rom_pending)
                color = card._cover_button.icon().pixmap(100, 100).toImage().pixelColor(50, 50)
                self.assertGreater(color.blue(), 200)
                self.assertLess(color.red(), 30)
            finally:
                release.set()
                wait_until(lambda: not self.loader._rom_pending)
                card.close()

    def test_missing_art_has_a_console_thumbnail(self) -> None:
        card = unmatched_rom_card.UnmatchedRomCard(self.rom, 'Wii', cover_size=100)
        try:
            self.assertFalse(card._cover_button.icon().isNull())
            self.assertEqual(card._cover_button.text(), '')
            card._on_rom_cover_ready(7, None)
            self.assertFalse(card._cover_button.icon().isNull())
        finally:
            card.close()
