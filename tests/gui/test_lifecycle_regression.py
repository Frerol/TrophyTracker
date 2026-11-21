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

from PySide6.QtCore import Qt, QTimer
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
        for key in ('home', 'library', 'lists', 'settings'):
            page = self.window.destination(key)
            self.window.navigate(key)
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
        home = self.window.destination('home')
        self.window.navigate('home')
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
        items = self.window._sidebar.items
        for key, item in items.items():
            item.click()
            self._pump()
            self.assertIs(self.window._pages.currentWidget(), self.window.destination(key))
            self.assertTrue(item.isChecked())
            self.assertEqual(sum(other.isChecked() for other in items.values()), 1)

        for key in items:
            self.window.navigate(key)
            self._pump()
            self.assertIs(self.window._pages.currentWidget(), self.window.destination(key))
            self.assertTrue(items[key].isChecked())

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
        for _ in range(100):
            self._pump(10)
            if not self.window.isVisible():
                break
        self.assertFalse(self.window.isVisible())
        self.assertTrue(stopped.is_set())
        self.assertNotIn(worker, self.window.app_context.workers.active())

        # `aboutToQuit` can call shutdown again; it must not raise or restart
        # anything.
        self.window.app_context.shutdown()
        self.assertEqual(self.window.app_context.workers.active(), ())

    def _close_and_wait(self):
        before = time.monotonic()
        self.window.close()
        self.assertLess(time.monotonic() - before, 0.5)
        for _ in range(200):
            self._pump(10)
            if not self.window.isVisible():
                break
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.window.app_context.is_idle())

    def test_close_gives_up_on_a_worker_that_outlives_the_shutdown_budget(self):
        # A worker that ignores cancellation must not keep the window open
        # (disabled) forever: after the budget it is left lingering and the
        # close goes through.
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def stuck():
            entered.set()
            release.wait(5)
        worker = ServiceWorker(stuck)
        with patch('retrocheevos.gui.main_window.SHUTDOWN_TIMEOUT_MS', 150):
            self.window.app_context.workers.start(worker)
            self.assertTrue(entered.wait(1))
            self.window.close()
            self.assertTrue(self.window.isVisible())
            for _ in range(100):
                self._pump(10)
                if not self.window.isVisible():
                    break
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window.app_context.is_idle())
        release.set()
        worker.wait(2000)

    def test_close_cancels_shared_api_penalty_without_sending_request(self):
        from retrocheevos.api.client import RequestPacer, RetroAchievementsClient
        from unittest.mock import Mock
        pacer = RequestPacer()
        pacer.penalize(120)
        entered = Event()
        client = RetroAchievementsClient('synthetic', 'synthetic')
        client._session.get = Mock()
        def request():
            entered.set()
            client.get('synthetic.php')
        with patch('retrocheevos.api.client.pacer', pacer):
            worker = ServiceWorker(request)
            self.window.app_context.workers.start(worker)
            self.assertTrue(entered.wait(1))
            self._close_and_wait()
        client._session.get.assert_not_called()

    def test_close_waits_asynchronously_for_an_active_image_download(self):
        from retrocheevos.models.game import Game
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def download(_game):
            entered.set()
            if not release.wait(3):
                raise TimeoutError('test download was not released')
            return None
        loader = self.window.app_context.create_image_loader()
        with patch('retrocheevos.gui.image_loader.ensure_game_image_cached', side_effect=download):
            loader.request(Game(id=1, title='synthetic', console_id=7, has_achievements=True))
            self.assertTrue(entered.wait(1))
            self.window.close()
            self.assertTrue(self.window.isVisible())
            self.assertFalse(self.window.isEnabled())
            QTimer.singleShot(50, release.set)
            self._close_and_wait()

    def test_close_during_sync_preserves_an_already_committed_console(self):
        from retrocheevos.api.client import RetroAchievementsClient
        from retrocheevos.services import sync_service
        from retrocheevos.api.exceptions import RateLimitError
        from retrocheevos.database.repositories.console_repository import ConsoleRepository
        first = RetroAchievementsClient('synthetic', 'synthetic')
        calls = 0
        paused = Event()
        def consoles():
            nonlocal calls
            calls += 1
            if calls == 1:
                from retrocheevos.api.games import RawConsole
                return [RawConsole(id=7, name='NES')]
            paused.set()
            raise RateLimitError('test penalty', retry_after=120)
        def sync(should_cancel):
            sync_service.sync_consoles(first, should_cancel)
            sync_service.sync_consoles(first, should_cancel)
        with patch('retrocheevos.services.sync_service.GamesClient.list_console_ids', side_effect=consoles):
            worker = ServiceWorker(sync, cancellable=True)
            self.window.app_context.workers.start(worker)
            self.assertTrue(paused.wait(1))
            self._close_and_wait()
        with db.get_connection() as connection:
            self.assertIsNotNone(ConsoleRepository(connection).get_by_id(7))
        self.assertEqual(calls, 2)

    def test_close_during_scan_preserves_previously_recorded_rom(self):
        from retrocheevos.services import library_service
        from tests.services.test_wii_rvz_scan import rvz_header
        root = self.database.parent / 'roms'
        root.mkdir()
        for name in ('first.rvz', 'second.rvz'):
            (root / name).write_bytes(rvz_header(2))
        folder = library_service.add_rom_folder(str(root), 19)
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        calls = 0
        def hash_rom(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                release.wait(3)
            return ''
        with patch('retrocheevos.services.library_service._hash_in_place', side_effect=hash_rom):
            worker = ServiceWorker(library_service.scan_rom_folder, folder.id, cancellable=True)
            self.window.app_context.workers.start(worker)
            self.assertTrue(entered.wait(1))
            self.assertEqual(len(library_service.list_installed_roms()), 1)
            QTimer.singleShot(50, release.set)
            self._close_and_wait()
        self.assertGreaterEqual(len(library_service.list_installed_roms()), 1)

    def test_close_during_activity_waits_for_inflight_request_then_cancels(self):
        from retrocheevos.services import activity_feed_service
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def following(*args):
            entered.set()
            release.wait(3)
            return []
        with patch('retrocheevos.services.activity_feed_service.ProfileClient.get_users_i_follow', side_effect=following):
            worker = ServiceWorker(activity_feed_service.get_recent_activity_feed,
                                   Account('synthetic', 'synthetic', True), cancellable=True)
            self.window.app_context.workers.start(worker)
            self.assertTrue(entered.wait(1))
            QTimer.singleShot(50, release.set)
            self._close_and_wait()

    def test_process_exits_cleanly_after_close_with_inflight_worker(self):
        import os
        import subprocess
        import sys
        script = r"""
import sys
import time
from pathlib import Path
from threading import Event
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from retrocheevos.database import connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.workers import ServiceWorker
app = QApplication([])
create = db.create_connection
path = Path(sys.argv[1])
with patch.object(db, 'create_connection', lambda database_path=None: create(path)):
    initialize_database(path).close()
    with patch.object(MainWindow, '_start_update_check', lambda self: None):
        window = MainWindow()
    window.show()
    entered = Event()
    def inflight():
        entered.set()
        time.sleep(0.2)
    worker = ServiceWorker(inflight)
    window.app_context.workers.start(worker)
    assert entered.wait(1)
    QTimer.singleShot(0, window.close)
    QTimer.singleShot(5000, lambda: app.exit(9))
    result = app.exec()
    assert result == 0, result
    assert window.app_context.is_idle()
"""
        result = subprocess.run(
            [sys.executable, '-c', script, str(self.database.parent / 'child.db')],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Destroyed while thread', result.stderr)
        self.assertNotIn('Signal source has been deleted', result.stderr)

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
