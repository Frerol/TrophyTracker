"""Sidebar account area: menu contents, explicit selection and avatar guards (R18)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui import sidebar as sidebar_module
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.sidebar import AccountPanel, Sidebar, round_avatar
from retrocheevos.models.account import Account
from retrocheevos.services import session_service

_app = QApplication.instance() or QApplication([])


class SidebarTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'sidebar.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(path))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(path).close()
        patcher = patch('retrocheevos.services.credential_store.migrate_plaintext_keys')
        patcher.start()
        self.addCleanup(patcher.stop)

    def save(self, *names):
        for name in names:
            session_service.add_account(name, 'synthetic-key', activate=False)
        return {account.username: account for account in session_service.list_accounts()}


class AccountPanelMenuTests(SidebarTestCase):
    def panel(self, account):
        panel = AccountPanel()
        self.addCleanup(panel.deleteLater)
        panel.set_account(account)
        return panel

    def test_signed_in_menu_marks_and_selects_the_displayed_account(self):
        accounts = self.save('Alice', 'Bob')
        panel = self.panel(accounts['Alice'])
        menu = panel.build_menu()
        actions = [action for action in menu.actions() if not action.isSeparator()]
        self.assertEqual([a.text() for a in actions][1:], ['Manage accounts…', 'Sign out'])
        submenu = actions[0].menu()
        self.assertIn('Alice', submenu.title())
        choices = {action.text(): action for action in submenu.actions()}
        self.assertTrue(choices['Alice'].isChecked())
        self.assertFalse(choices['Bob'].isChecked())
        chosen, signed_out = [], []
        panel.account_chosen.connect(chosen.append)
        panel.sign_out_requested.connect(lambda: signed_out.append(True))
        choices['Bob'].trigger()
        actions[2].trigger()
        self.assertEqual(chosen, [accounts['Bob'].id])
        self.assertEqual(signed_out, [True])
        self.assertEqual(panel.name_text(), 'Alice')

    def test_signed_out_menu_offers_each_saved_account(self):
        accounts = self.save('Alice', 'Bob')
        panel = self.panel(None)
        self.assertEqual(panel.name_text(), sidebar_module.NO_ACCOUNT_TITLE)
        actions = [a for a in panel.build_menu().actions() if not a.isSeparator()]
        self.assertEqual([a.text() for a in actions], ['Display Alice', 'Display Bob', 'Add an account…'])
        chosen = []
        panel.account_chosen.connect(chosen.append)
        actions[1].trigger()
        self.assertEqual(chosen, [accounts['Bob'].id])

    def test_menu_without_accounts_leads_to_settings(self):
        panel = self.panel(None)
        actions = panel.build_menu().actions()
        self.assertEqual([a.text() for a in actions], ['Add an account…'])
        destinations = []
        panel.navigate_requested.connect(destinations.append)
        actions[0].trigger()
        self.assertEqual(destinations, ['settings'])

    def test_panel_has_accessible_name_and_shows_menu_on_click(self):
        accounts = self.save('Alice')
        panel = self.panel(accounts['Alice'])
        self.assertIn('Alice', panel.accessibleName())
        panel.click()
        self.assertIsNotNone(panel._menu)
        panel._menu.close()


class AvatarTests(SidebarTestCase):
    def test_round_avatar_has_requested_size_with_and_without_photo(self):
        fallback = round_avatar(None, 'alice', 40)
        self.assertEqual((fallback.width(), fallback.height()), (40, 40))
        photo = round_avatar(fallback, 'alice', 40, ratio=2.0)
        self.assertEqual(photo.width(), 80)

    def test_photo_results_cannot_land_on_another_account(self):
        context = AppContext()
        self.addCleanup(context.shutdown)
        bar = Sidebar(context)
        self.addCleanup(bar.deleteLater)
        alice = Account('Alice', '', True, id=1)
        bob = Account('Bob', '', True, id=2)
        context._active_account = alice
        bar.set_account(alice)
        old_generation = bar._photo_generation
        context._active_account = bob
        bar.set_account(bob)
        with patch.object(bar, '_on_photo_ready') as ready:
            bar._on_photo_ready_guarded('/old.png', old_generation, alice.id)
            ready.assert_not_called()
            bar._on_photo_ready_guarded('/bob.png', bar._photo_generation, alice.id)
            ready.assert_not_called()
            bar._on_photo_ready_guarded('/bob.png', bar._photo_generation, bob.id)
            ready.assert_called_once_with('/bob.png', bob.id)

    def test_refresh_avatar_requests_photo_once_stats_exist(self):
        context = AppContext()
        self.addCleanup(context.shutdown)
        bar = Sidebar(context)
        self.addCleanup(bar.deleteLater)
        alice = Account('Alice', '', True, id=1)
        context._active_account = alice
        with patch.object(sidebar_module.profile_service, 'get_profile_stats', return_value=None), \
             patch.object(context.workers, 'start') as start:
            bar.set_account(alice)
            start.assert_not_called()
        stats = type('Stats', (), {'user_pic_path': '/UserPic/Alice.png'})()
        with patch.object(sidebar_module.profile_service, 'get_profile_stats', return_value=stats), \
             patch.object(context.workers, 'start') as start:
            bar.refresh_avatar()
            start.assert_called_once()
            self.assertEqual(start.call_args.kwargs['key'], ('shell', 'photo', bar._photo_generation))


if __name__ == '__main__':
    unittest.main()
