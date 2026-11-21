"""Awards view (D7): sections, lazy badge images, events banner and navigation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.pages import awards_view
from retrocheevos.gui.pages.awards_view import AwardsView, BadgeListModel
from retrocheevos.models.profile import Badge
from retrocheevos.services import notification_service
from tests.gui.test_navigation import close_window, patch_live_calls

_app = QApplication.instance() or QApplication([])


class FakeLoader(QObject):
    badge_image_ready = Signal(int, object)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request_badge(self, badge_id, image_path):
        self.requests.append((badge_id, image_path))


def badges(count, *, event=False):
    return [Badge(1, f'Award {i}', True, f'/Images/{i}.png', is_event=event, id=i) for i in range(count)]


class BadgeListModelTests(unittest.TestCase):
    def setUp(self):
        self.loader = FakeLoader()
        self.model = BadgeListModel(self.loader)
        self.model.set_badges(badges(300))

    def decoration(self, row):
        return self.model.data(self.model.index(row), Qt.ItemDataRole.DecorationRole)

    def test_images_are_requested_only_for_painted_rows_and_once(self):
        self.assertEqual(self.model.rowCount(), 300)
        self.assertEqual(self.loader.requests, [])
        for row in (0, 1, 2, 1, 0):
            self.assertIsInstance(self.decoration(row), QPixmap)
        self.assertEqual([request[0] for request in self.loader.requests], [0, 1, 2])
        self.assertEqual(self.model.data(self.model.index(5)), 'Award 5')

    def test_loaded_images_are_cached_bounded_and_failures_not_retried(self):
        changed = []
        self.model.dataChanged.connect(lambda top, _bottom, _roles: changed.append(top.row()))
        image = QPixmap(128, 128)
        image.fill(Qt.GlobalColor.yellow)
        for row in range(awards_view.MAX_CACHED_BADGE_IMAGES + 20):
            self.decoration(row)
            self.loader.badge_image_ready.emit(row, image)
        self.assertLessEqual(len(self.model._cache), awards_view.MAX_CACHED_BADGE_IMAGES)
        self.assertEqual(self.decoration(awards_view.MAX_CACHED_BADGE_IMAGES + 19).width(), awards_view.BADGE_ICON)
        self.assertIn(5, changed)
        requests = len(self.loader.requests)
        self.decoration(250)
        self.loader.badge_image_ready.emit(250, None)
        self.decoration(250)
        self.assertEqual(len(self.loader.requests), requests + 1)
        # A late result for a row nobody requested is ignored.
        self.loader.badge_image_ready.emit(299, image)
        self.assertNotIn(299, self.model._cache)


class AwardsNavigationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'awards.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(self.database))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.database).close()
        patch_live_calls(self)
        with db.get_connection(self.database) as c:
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'alice', '', 1)")
            c.execute("INSERT INTO consoles(id, name) VALUES(101, 'Events')")
            for index in range(4):
                c.execute(
                    "INSERT INTO badges(account_id, name, image_path, owned, is_event) VALUES(1, ?, ?, 1, ?)",
                    (f'Award {index}', f'/Images/{index}.png', 1 if index == 3 else 0),
                )
            c.execute("INSERT INTO games(id, title, console_id, has_achievements) VALUES(900, 'Event A', 101, 1)")
        with patch.object(MainWindow, '_start_update_check', new=lambda self: None):
            self.window = MainWindow()
        self.addCleanup(close_window, self.window)
        self.home = self.window.destination('home')

    def test_home_button_opens_awards_and_back_restores_home(self):
        self.home._search_input.setText('')
        with patch.object(self.home, 'refresh') as refresh:
            self.home._awards_button.click()
            self.assertTrue(self.window.detail_open())
            view = self.window._pages.currentWidget()
            self.assertIsInstance(view, AwardsView)
            self.assertTrue(self.window._sidebar.items['home'].isChecked())
            self.assertEqual(view._tabs.tabText(0), 'Badges (3)')
            self.assertEqual(view._tabs.tabText(1), 'Event awards (1)')
            self.assertEqual([b.name for b in view._badges_model.badges()], ['Award 0', 'Award 1', 'Award 2'])
            self.assertTrue(view._badges_empty.isHidden())
            view.back_requested.emit()
            refresh.assert_not_called()
        self.assertIs(self.window._pages.currentWidget(), self.home)
        self.assertFalse(self.window.detail_open())

    def test_banner_marks_events_read_and_updates_home(self):
        notification_service.record_new_events(1, [(900, 'Event A')])
        self.home.refresh()
        self.assertFalse(self.home._awards_unread.isHidden())
        view = self.window.open_awards()
        self.assertFalse(view._banner.isHidden())
        self.assertIn('Event A', view._banner.text())
        view._banner.click()
        self.assertTrue(view._banner.isHidden())
        self.assertEqual(notification_service.list_unread_events(1), [])
        self.assertTrue(self.home._awards_unread.isHidden())

    def test_empty_account_shows_sync_hint(self):
        with db.get_connection(self.database) as c:
            c.execute("DELETE FROM badges")
        view = self.window.open_awards()
        self.assertFalse(view._badges_empty.isHidden())
        self.assertEqual(view._badges_empty.text(), awards_view.EMPTY_AWARDS_TEXT)
        self.assertTrue(view._badges_view.isHidden())

    def test_account_change_closes_the_awards_view(self):
        self.window.open_awards()
        self.window.app_context._active_account = None
        self.window.app_context.active_account_changed.emit(None)
        self.assertFalse(self.window.detail_open())


if __name__ == '__main__':
    unittest.main()
