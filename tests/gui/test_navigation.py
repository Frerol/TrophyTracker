"""Sidebar navigation, detail routes and view-state preservation (R18)."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QVBoxLayout, QWidget

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui import view_state
from retrocheevos.gui.main_window import MINIMUM_HEIGHT, MINIMUM_WIDTH, MainWindow
from retrocheevos.gui.pages import library_page
from retrocheevos.models.account import Account

_app = QApplication.instance() or QApplication([])

DESTINATIONS = ('home', 'library', 'lists', 'settings')


def patch_live_calls(test):
    """Replace live API calls made by Home and the sidebar with empty results."""
    from retrocheevos.models.activity_feed import ActivityFeedResult
    for target, value in (
        ('retrocheevos.services.sync_service.sync_profile_if_needed', False),
        ('retrocheevos.services.activity_feed_service.get_recent_activity_feed',
         ActivityFeedResult(entries=[], failed_usernames=[])),
        ('retrocheevos.services.now_playing_service.refresh_now_playing', None),
        ('retrocheevos.services.image_service.ensure_user_pic_cached', None),
        ('retrocheevos.gui.image_loader.ensure_game_image_cached', None),
        ('retrocheevos.gui.image_loader.ensure_rom_image_cached', None),
        ('retrocheevos.gui.image_loader.ensure_badge_image_cached', None),
    ):
        patcher = patch(target, return_value=value)
        patcher.start()
        test.addCleanup(patcher.stop)


def close_window(window):
    """Close `window` and let its background work drain, as the real close does."""
    window.close()
    deadline = time.monotonic() + 5
    while not window.app_context.is_idle() and time.monotonic() < deadline:
        QTest.qWait(10)
    window.app_context.shutdown()


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
        patch_live_calls(self)
        with patch.object(MainWindow, "_start_update_check", new=lambda self: None):
            self.window = MainWindow()
        self.addCleanup(close_window, self.window)
        self.sidebar = self.window._sidebar
        self.home = self.window.destination('home')

    def _pump(self, ms=20):
        QTest.qWait(ms)

    def test_sidebar_items_reach_every_page_and_select_only_current_destination(self):
        self.assertEqual(tuple(self.sidebar.items), DESTINATIONS)
        for key, item in self.sidebar.items.items():
            item.click()
            self.assertIs(self.window._pages.currentWidget(), self.window.destination(key))
            self.assertEqual(self.window.current_destination(), key)
            self.assertTrue(item.isChecked())
            self.assertEqual(sum(other.isChecked() for other in self.sidebar.items.values()), 1)

    def test_keyboard_shortcuts_navigate(self):
        for index, key in enumerate(DESTINATIONS, start=1):
            shortcut = self.sidebar.shortcuts[key]
            self.assertEqual(shortcut.key().toString(), f'Ctrl+{index}')
            shortcut.activated.emit()
            self.assertEqual(self.window.current_destination(), key)
            self.assertTrue(self.sidebar.items[key].isChecked())

    def test_account_menu_navigation_updates_selection(self):
        self.sidebar.account_panel.navigate_requested.emit('settings')
        self.assertEqual(self.window.current_destination(), 'settings')
        self.assertTrue(self.sidebar.items['settings'].isChecked())

    def test_home_search_survives_navigating_away_and_back(self):
        self.window.navigate('home')
        self.home._search_input.setText('mario')
        self.assertTrue(self.home._results_expanded())
        self.window.navigate('library')
        self.window.navigate('home')
        self.assertEqual(self.home._search_input.text(), 'mario')
        self.assertEqual(self.home._explorer_page._search_input.text(), 'mario')
        self.assertTrue(self.home._results_expanded())

    def test_selecting_home_again_returns_to_its_root(self):
        self.window.navigate('home')
        self.home._search_input.setText('mario')
        self.sidebar.items['home'].click()
        self.assertEqual(self.home._search_input.text(), '')
        self.assertEqual(self.home._explorer_page._search_input.text(), '')
        self.assertFalse(self.home._results_expanded())
        self.assertTrue(self.sidebar.items['home'].isChecked())

    def test_back_from_detail_restores_origin_without_refreshing(self):
        self.window.navigate('library')
        library = self.window.destination('library')
        detail = QLabel('detail')
        with patch.object(library, 'refresh') as refresh:
            self.window.open_detail(detail)
            self.assertIs(self.window._pages.currentWidget(), detail)
            self.assertTrue(self.window.detail_open())
            self.assertTrue(self.sidebar.items['library'].isChecked())
            self.assertTrue(self.window.go_back())
            refresh.assert_not_called()
        self.assertIs(self.window._pages.currentWidget(), library)
        self.assertFalse(self.window.detail_open())
        self.assertEqual(self.window._pages.count(), len(DESTINATIONS))
        self.assertFalse(self.window.go_back())

    def test_nested_details_go_back_one_at_a_time(self):
        self.window.navigate('lists')
        first, second = QLabel('first'), QLabel('second')
        self.window.open_detail(first)
        self.window.open_detail(second)
        self.window.go_back()
        self.assertIs(self.window._pages.currentWidget(), first)
        self.window.go_back()
        self.assertIs(self.window._pages.currentWidget(), self.window.destination('lists'))

    def test_sidebar_selection_closes_open_details(self):
        self.window.navigate('home')
        self.window.open_detail(QLabel('detail'))
        self.sidebar.items['lists'].click()
        self.assertFalse(self.window.detail_open())
        self.assertIs(self.window._pages.currentWidget(), self.window.destination('lists'))
        self.assertEqual(self.window._pages.count(), len(DESTINATIONS))

    def test_account_change_closes_details_and_resets_home_search(self):
        self.window.navigate('home')
        self.home._search_input.setText('mario')
        self.window.open_detail(QLabel('detail'))
        self.window.app_context._active_account = Account('Alice', '', True, id=1)
        self.window.app_context.active_account_changed.emit(self.window.app_context.active_account)
        self.assertFalse(self.window.detail_open())
        self.assertIs(self.window._pages.currentWidget(), self.home)
        self.assertEqual(self.home._search_input.text(), '')
        self.assertFalse(self.home._results_expanded())
        self.assertEqual(self.sidebar.account_panel.name_text(), 'Alice')

    def test_shell_fits_the_minimum_window_without_clipping(self):
        self.assertEqual(self.window.minimumSize().width(), MINIMUM_WIDTH)
        self.assertEqual(self.window.minimumSize().height(), MINIMUM_HEIGHT)
        self.window.showNormal()
        self.window.resize(MINIMUM_WIDTH, MINIMUM_HEIGHT)
        self._pump(50)
        bounds = self.sidebar.rect()
        widgets = [*self.sidebar.items.values(), self.sidebar.account_panel, self.sidebar.version_label]
        for widget in widgets:
            self.assertTrue(widget.isVisible(), widget)
            geometry = QRect(widget.mapTo(self.sidebar, widget.rect().topLeft()), widget.size())
            self.assertTrue(bounds.contains(geometry), (widget, geometry, bounds))
        self.assertGreater(self.window._pages.width(), MINIMUM_WIDTH - self.sidebar.width() - 1)


class ScrollRestoreTests(unittest.TestCase):
    def test_restore_scroll_later_applies_after_rebuild_and_clamps(self):
        area = QScrollArea()
        area.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        for index in range(80):
            layout.addWidget(QLabel(f'row {index}'))
        area.setWidget(content)
        area.resize(300, 200)
        area.show()
        self.addCleanup(area.close)
        QTest.qWait(20)
        bar = area.verticalScrollBar()
        bar.setValue(bar.maximum() // 2)
        value = bar.value()
        self.assertGreater(value, 0)
        # Rebuild the content, which resets the range until it is laid out.
        while layout.count():
            layout.takeAt(0).widget().deleteLater()
        for index in range(80):
            layout.addWidget(QLabel(f'new row {index}'))
        view_state.restore_scroll_later(area, value)
        QTest.qWait(20)
        self.assertEqual(bar.value(), value)
        view_state.restore_scroll_later(area, 10**6)
        QTest.qWait(20)
        self.assertEqual(bar.value(), bar.maximum())

    def test_library_refresh_keeps_scroll_only_for_the_same_account(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = Path(temporary.name) / "library.db"
        create = db.create_connection
        patcher = patch.object(db, "create_connection", lambda database_path=None: create(database))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(database).close()
        from retrocheevos.gui.app_context import AppContext
        context = AppContext()
        self.addCleanup(context.shutdown)
        page = library_page.LibraryPage(context)
        self.addCleanup(page.close)
        with patch.object(library_page, 'restore_scroll_later') as restore:
            page.refresh()
            page.refresh()
            self.assertEqual(restore.call_count, 2)
            context._active_account = Account('Alice', '', True, id=1)
            page.refresh()
            self.assertEqual(restore.call_count, 2)
            page.refresh()
            self.assertEqual(restore.call_count, 3)


class FlowLayoutTests(unittest.TestCase):
    def test_items_wrap_inside_narrow_widths_and_skip_hidden_ones(self):
        from PySide6.QtWidgets import QPushButton
        from retrocheevos.gui.flow_layout import FlowLayout
        host = QWidget()
        self.addCleanup(host.deleteLater)
        layout = FlowLayout(host)
        buttons = [QPushButton(f'Button number {index}') for index in range(6)]
        for button in buttons:
            layout.addWidget(button)
        widest = max(button.sizeHint().width() for button in buttons)
        one_row = layout.heightForWidth(layout.sizeHint().width())
        self.assertEqual(one_row, max(button.sizeHint().height() for button in buttons))
        self.assertGreater(layout.heightForWidth(widest), one_row * 5)
        self.assertEqual(layout.minimumSize().width(), max(b.minimumSizeHint().width() for b in buttons))
        host.resize(widest * 2 + 20, layout.heightForWidth(widest * 2 + 20))
        layout.setGeometry(host.rect())
        for button in buttons:
            self.assertTrue(host.rect().contains(button.geometry()), button.geometry())
        buttons[0].hide()
        self.assertLessEqual(layout.heightForWidth(widest * 2 + 20), host.height())


if __name__ == '__main__':
    unittest.main()
