"""Regression tests for page callbacks that referenced removed helpers.

The failure only surfaced as an unhandled exception in the log of a real
session: every finished Library scan raised `AttributeError`, leaving the
scan buttons disabled. (The Home avatar hover menu it was found with was
replaced by the sidebar account menu in R18.)
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages import library_page
from retrocheevos.gui.pages.library_page import LibraryPage
from retrocheevos.models.library import RehashResult, RomFolderScanResult

_app = QApplication.instance() or QApplication([])


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
        self.page._begin_job()
        self.assertFalse(self.page._scan_button.isEnabled())
        self.assertFalse(self.page._cancel_button.isHidden())

    def assert_buttons_reset(self):
        self.assertEqual(self.page._scan_button.text(), library_page.SCAN_BUTTON_TEXT)
        self.assertTrue(self.page._scan_button.isEnabled())
        self.assertTrue(self.page._scan_all_action.isEnabled())
        self.assertTrue(self.page._rehash_action.isEnabled())
        self.assertTrue(self.page._cancel_button.isHidden())

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
        self.page._on_job_cancelled()
        self.assert_buttons_reset()
        self.assertIn('Cancelled', self.page._scan_status_label.text())


if __name__ == "__main__":
    unittest.main()
