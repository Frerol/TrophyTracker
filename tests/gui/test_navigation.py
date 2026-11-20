"""Persistent navigation must stay synchronized with programmatic navigation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class NavigationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = Path(temporary.name) / "navigation.db"
        create = db.create_connection
        patcher = patch.object(db, "create_connection", lambda database_path=None: create(database))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(database).close()
        with patch.object(MainWindow, "_start_update_check", new=lambda self: None):
            self.window = MainWindow()
        self.addCleanup(self.window.close)

    def test_buttons_reach_every_page_and_select_only_current_destination(self):
        for page, button in self.window._navigation_buttons.items():
            button.click()
            self.assertIs(self.window._pages.currentWidget(), page)
            self.assertTrue(button.isChecked())
            self.assertEqual(sum(item.isChecked() for item in self.window._navigation_buttons.values()), 1)

    def test_menu_navigation_updates_persistent_selection(self):
        for name, page in self.window._menu_pages.items():
            self.window._on_menu_navigate(name)
            self.assertIs(self.window._pages.currentWidget(), page)
            self.assertTrue(self.window._navigation_buttons[page].isChecked())
        self.window._show_page(self.window._nav_pages[0])
        self.assertTrue(self.window._navigation_buttons[self.window._nav_pages[0]].isChecked())
