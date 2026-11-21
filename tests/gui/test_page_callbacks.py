"""Regression tests for page callbacks that referenced removed helpers.

Both failures only surfaced as unhandled exceptions in the log of a real
session: hovering the Home avatar raised `NameError`, and every finished
Library scan raised `AttributeError`, leaving the scan buttons disabled.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages import home_page, library_page
from retrocheevos.gui.pages.library_page import LibraryPage
from retrocheevos.models.library import RehashResult, RomFolderScanResult

_app = QApplication.instance() or QApplication([])


class HoverMenuButtonTests(unittest.TestCase):
    def test_enter_starts_the_hover_delay(self):
        button = home_page._HoverMenuButton("Menu")
        self.addCleanup(button.deleteLater)
        point = QPointF(1, 1)
        button.enterEvent(QEnterEvent(point, point, point))
        self.assertTrue(button._hover_timer.isActive())
        self.assertEqual(button._hover_timer.interval(), home_page.HOVER_MENU_DELAY_MS)
        button.leaveEvent(QEvent(QEvent.Type.Leave))
        self.assertFalse(button._hover_timer.isActive())


class LibraryScanCallbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        create = db.create_connection
        path = Path(temp.name) / "library.db"
        patcher = patch.object(db, "create_connection", lambda database_path=None: create(path))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(path).close()
        self.context = AppContext()
        self.page = LibraryPage(self.context)
        self.addCleanup(self.page.close)
        self.addCleanup(self.context.shutdown)

    def start_busy(self):
        self.page._set_scan_buttons_enabled(False)
        self.page._scan_button.setText("Scanning...")
        self.page._scan_all_button.setText("Scanning...")
        self.page._rehash_button.setText("Scanning...")

    def assert_buttons_reset(self):
        self.assertEqual(self.page._scan_button.text(), library_page.SCAN_BUTTON_TEXT)
        self.assertEqual(self.page._scan_all_button.text(), library_page.SCAN_ALL_BUTTON_TEXT)
        self.assertEqual(self.page._rehash_button.text(), library_page.REHASH_BUTTON_TEXT)
        for button in (self.page._scan_button, self.page._scan_all_button, self.page._rehash_button):
            self.assertTrue(button.isEnabled())

    def test_finished_scan_restores_the_buttons(self):
        self.start_busy()
        self.page._on_scan_done(RomFolderScanResult(
            rom_folder_id=1, recorded=[], already_known_count=0,
            ambiguous_paths=[], unrecognized_paths=[],
        ))
        self.assert_buttons_reset()

    def test_finished_rehash_restores_the_buttons(self):
        self.start_busy()
        self.page._on_rehash_done(RehashResult(
            checked=0, changed=0, newly_matched=0, missing=[], failed=[],
        ))
        self.assert_buttons_reset()

    def test_cancelled_scan_restores_the_buttons(self):
        self.start_busy()
        self.page._reset_scan_button()
        self.assert_buttons_reset()


if __name__ == "__main__":
    unittest.main()
