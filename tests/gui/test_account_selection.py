"""Saved credentials never implicitly choose a different displayed account."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMenu

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.settings_page import SettingsPage
from retrocheevos.gui.pages.home_page import HomePage
from retrocheevos.services import session_service

_app = QApplication.instance() or QApplication([])


class AccountSelectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'accounts.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.path).close()
        patcher = patch('retrocheevos.services.credential_store.migrate_plaintext_keys')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.context = AppContext()
        self.page = SettingsPage(self.context)
        self.addCleanup(self.page.close)
        self.addCleanup(self.context.shutdown)

    def save(self, name):
        self.page._username_input.setText(name)
        self.page._api_key_input.setText('synthetic-key')
        self.page._on_add_account()

    def display(self, name):
        for row in range(self.page._accounts_list.count()):
            item = self.page._accounts_list.item(row)
            if item.text().split(' (')[0] == name:
                self.page._accounts_list.setCurrentItem(item)
                break
        self.page._on_switch_account()

    def test_saving_requires_explicit_selection_and_preserves_current_choice(self):
        self.save('Alice')
        self.save('Bob')
        self.assertIsNone(self.context.active_account)
        self.display('Alice')
        self.assertEqual(self.context.active_account.username, 'Alice')
        self.save('Carol')
        self.assertEqual(self.context.active_account.username, 'Alice')
        self.display('Bob')
        self.assertEqual(self.context.active_account.username, 'Bob')
        self.assertEqual([a.username for a in session_service.list_accounts() if a.is_active], ['Bob'])
        # Restart restores the explicit choice, not the first saved account.
        self.assertEqual(AppContext().active_account.username, 'Bob')
        session_service.logout()
        self.context.refresh_active_account()
        self.assertIsNone(self.context.active_account)
        self.assertEqual(len(session_service.list_accounts()), 3)

    def test_invalid_selection_preserves_current_account(self):
        self.save('Alice')
        self.display('Alice')
        with self.assertRaises(ValueError):
            session_service.switch_account(999)
        self.assertEqual(session_service.get_active_account().username, 'Alice')

    def test_stale_settings_and_avatar_choices_report_error_without_logout(self):
        from retrocheevos.gui.main_window import MainWindow
        from types import SimpleNamespace
        self.save('Alice')
        self.display('Alice')
        self.page._accounts_list.setCurrentRow(0)
        item = self.page._accounts_list.currentItem()
        item.setData(Qt.ItemDataRole.UserRole, 999)
        with patch('retrocheevos.gui.pages.settings_page.QMessageBox.warning') as warning:
            self.page._on_switch_account()
            warning.assert_called_once()
        with patch('retrocheevos.gui.main_window.QMessageBox.warning') as warning:
            MainWindow._on_login(SimpleNamespace(app_context=self.context), 999)
            warning.assert_called_once()
        self.assertEqual(self.context.active_account.username, 'Alice')
        self.assertEqual(session_service.get_active_account().username, 'Alice')

    def test_avatar_menu_marks_and_selects_the_displayed_account(self):
        self.save('Alice')
        self.save('Bob')
        self.display('Alice')
        home = HomePage(self.context)
        self.addCleanup(home.close)
        menu = QMenu()
        self.addCleanup(menu.close)
        home._add_session_actions(menu)
        submenu = menu.actions()[0].menu()
        self.assertIn('Alice', submenu.title())
        actions = {action.text(): action for action in submenu.actions()}
        self.assertTrue(actions['Alice'].isChecked())
        self.assertFalse(actions['Bob'].isChecked())
        chosen = []
        home.login_requested.connect(chosen.append)
        actions['Bob'].trigger()
        self.assertEqual(chosen, [next(a.id for a in session_service.list_accounts() if a.username == 'Bob')])
