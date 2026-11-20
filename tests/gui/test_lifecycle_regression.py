"""GUI lifecycle regressions: fullscreen, navigation and worker lifetime.

The Explorer redesign removed `setIndexWidget()` after a native crash
(`STATUS_FATAL_USER_CALLBACK_EXCEPTION` inside `Qt6Widgets.dll`) that was
triggered by entering fullscreen from Explorer. These tests are the
reproducible guard for that class of failure and for the worker-ownership
contract: they repeat fullscreen, navigation and worker-lifetime scenarios
against every page, including Home's embedded Explorer, and close the window
while a worker is still running.

Run offscreen (`QT_QPA_PLATFORM=offscreen`), as the CI test job does.
"""

import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.account import Account
from retrocheevos.models.activity_feed import ActivityFeedResult
from retrocheevos.utils.cancellation import OperationCancelled

_app = QApplication.instance() or QApplication([])

# Long enough for a queued page refresh or a window-state change to be
# delivered through the offscreen event loop.
PUMP_MS = 30


def _blocking_work(should_cancel) -> None:
    """Run until cancellation is requested, then stop at a safe boundary."""
    while not should_cancel():
        time.sleep(0.01)
    raise OperationCancelled()


class LifecycleRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        # Qt routes exceptions raised by Python slots through excepthook
        # instead of unittest; turn those into failures as well.
        qt_errors = []
        hook = patch('sys.excepthook', lambda *error: qt_errors.append(error))
        hook.start()
        self.addCleanup(hook.stop)
        self.addCleanup(lambda: self.assertEqual(qt_errors, []))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = Path(temporary.name) / "lifecycle.db"
        create = db.create_connection
        patcher = patch.object(db, "create_connection", lambda database_path=None: create(database))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.database = database
        initialize_database(database).close()
        with patch.object(MainWindow, "_start_update_check", new=lambda self: None):
            self.window = MainWindow()
        self.window.show()
        self.addCleanup(self.window.close)

    def _pump(self, ms: int = PUMP_MS) -> None:
        QTest.qWait(ms)
        _app.processEvents()

    def test_fullscreen_toggle_on_every_page_including_embedded_explorer(self) -> None:
        """The original crash path: fullscreen entered while Explorer is shown."""
        # Exercise the real SQLite -> background snapshot -> model -> delegates
        # path, with enough matching games to paint rows and scroll the table.
        with db.get_connection(self.database) as connection:
            connection.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'lifecycle', '', 1)")
            connection.execute("INSERT INTO consoles(id, name) VALUES(1, 'NES')")
            connection.executemany(
                "INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, 1, 1)",
                [(key, f'Mario {key:02d}') for key in range(1, 41)] + [(41, 'Zelda')],
            )
            connection.execute("INSERT INTO game_completion(account_id, game_id, percent_complete) VALUES(1, 1, 25)")
        # Disable only live API/artwork calls, preserving real database reads,
        # worker delivery, table painting and page navigation.
        for target, value in (
            ('retrocheevos.services.sync_service.sync_profile_if_needed', False),
            ('retrocheevos.services.activity_feed_service.get_recent_activity_feed', ActivityFeedResult(entries=[], failed_usernames=[])),
            ('retrocheevos.services.now_playing_service.refresh_now_playing', None),
            ('retrocheevos.gui.image_loader.ensure_game_image_cached', None),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window.app_context._active_account = Account('lifecycle', '', True, id=1)
        # Close workers before stopping mocks, even if an assertion fails.
        self.addCleanup(self.window.close)
        pages = [self.window._nav_pages[0], *self.window._menu_pages.values()]
        for page in pages:
            self.window._show_page(page)
            self._pump()
            self.window.showFullScreen()
            self._pump()
            self.assertTrue(self.window.isFullScreen())
            self.window.showNormal()
            self._pump()
            self.assertFalse(self.window.isFullScreen())
            self.assertIs(self.window._pages.currentWidget(), page)

        # Enter fullscreen from Home's expanded Explorer, where the original
        # crash was reproduced.
        home = self.window._nav_pages[0]
        self.window._show_page(home)
        home._search_input.setText("mario")
        explorer = home._explorer_page
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (not explorer._search_debounce_timer.isActive()
                    and explorer._read_worker is None
                    and explorer._table_model.rowCount() == 40):
                break
            self._pump(10)
        self.assertTrue(home._results_expanded())
        self.assertTrue(explorer._table.isVisible())
        self.assertEqual(explorer._table_model.rowCount(), 40)
        self.assertEqual({row.game.id for row in explorer._current_results}, set(range(1, 41)))
        self.assertEqual(next(row.percent_complete for row in explorer._current_results if row.game.id == 1), 25)
        # Rendering the viewport forces paint-only delegates to run; repeat
        # the transition after scrolling so both initial and recycled rows run.
        for _ in range(3):
            for fullscreen in (True, False):
                if fullscreen:
                    self.window.showFullScreen()
                else:
                    self.window.showNormal()
                explorer._table.scrollToBottom()
                self._pump()
                self.assertEqual(self.window.isFullScreen(), fullscreen)
                self.assertTrue(explorer._table.isVisible())
                self.assertEqual(explorer._table_model.rowCount(), 40)
                self.assertFalse(explorer._table.viewport().grab().isNull())
                explorer._table.scrollToTop()
                self._pump()

    def test_navigation_reaches_every_destination_and_keeps_selection(self) -> None:
        for page, button in self.window._navigation_buttons.items():
            self.window._show_page(page)
            self._pump()
            self.assertIs(self.window._pages.currentWidget(), page)
            self.assertTrue(button.isChecked())
            self.assertEqual(
                sum(item.isChecked() for item in self.window._navigation_buttons.values()), 1
            )

        for key, page in self.window._menu_pages.items():
            self.window._on_menu_navigate(key)
            self._pump()
            self.assertIs(self.window._pages.currentWidget(), page)
            self.assertTrue(self.window._navigation_buttons[page].isChecked())

        self.window._navigate_home()
        self._pump()
        self.assertIs(self.window._pages.currentWidget(), self.window._nav_pages[0])

    def test_closing_the_window_stops_a_running_worker(self) -> None:
        """A close during a worker must not destroy a running QThread.

        The window's registry owns the worker and `shutdown()` cancels and
        waits for it; the worker must have stopped by the time `close()`
        returns, and a second shutdown must be a no-op.
        """
        started = Event()

        def work(should_cancel) -> None:
            started.set()
            _blocking_work(should_cancel)

        stopped = Event()
        worker = ServiceWorker(work, cancellable=True)
        worker.finished.connect(stopped.set, Qt.ConnectionType.DirectConnection)
        self.window.app_context.workers.start(worker, key=("test", "lifecycle"))
        for _ in range(200):
            if started.is_set():
                break
            self._pump(5)
        self.assertTrue(started.is_set())
        self.assertIn(worker, self.window.app_context.workers.active())

        self.window.close()
        self._pump()
        self.assertTrue(stopped.is_set())
        self.assertNotIn(worker, self.window.app_context.workers.active())

        # `aboutToQuit` can call shutdown again; it must not raise or restart
        # anything.
        self.window.app_context.shutdown()
        self.assertEqual(self.window.app_context.workers.active(), ())

    def test_registry_refuses_new_workers_after_shutdown(self) -> None:
        self.window.app_context.shutdown()
        worker = ServiceWorker(lambda: None)
        self.window.app_context.workers.start(worker, key=("test", "late"))
        self._pump()
        self.assertFalse(worker.isRunning())
        self.assertEqual(self.window.app_context.workers.active(), ())

    def test_shutdown_releases_image_loaders(self) -> None:
        loader = self.window.app_context.create_image_loader()
        self.window.app_context.shutdown()
        self.assertTrue(loader._shutting_down)
        # The loader is owned by the context; a second shutdown must not touch
        # it again (idempotence) and must not raise a deleted-signal error.
        self.window.app_context.shutdown()
        self.assertEqual(self.window.app_context.workers.active(), ())


if __name__ == "__main__":
    unittest.main()
