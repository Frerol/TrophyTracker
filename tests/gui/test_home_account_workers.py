"""Controlled delayed callbacks exercise Home account isolation and job ownership."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.home_page import HomePage, HOME_WORKER_ACTIVITY
from retrocheevos.gui.pages.settings_page import SettingsPage
from retrocheevos.models.account import Account
from retrocheevos.models.activity_feed import ActivityFeedResult
from retrocheevos.services import job_coordinator as jobs
from tests.gui.test_activity_rendering import entry

_app = QApplication.instance() or QApplication([])


class ControlledWorkers:
    def __init__(self):
        self.pending = {}
        self.all = []

    def start(self, worker, key=None):
        self.pending[key] = worker
        self.all.append(worker)
        return worker

    def has_key(self, key):
        return key in self.pending

    def cancel_key(self, key):
        if key in self.pending:
            self.pending[key].cancel()

    def finish(self, key):
        worker = self.pending.pop(key)
        worker.finished.emit()

    def shutdown(self, **kwargs):
        pass


class HomeAccountWorkerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        create = db.create_connection
        path = Path(temp.name) / 'home.db'
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(path))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(path).close()
        self.context = AppContext()
        self.workers = ControlledWorkers()
        self.context.workers = self.workers
        self.home = HomePage(self.context)
        self.addCleanup(self.home.close)
        self.addCleanup(self.context.shutdown)
        jobs.reset()
        self.addCleanup(jobs.reset)
        self.alice = Account('Alice', 'synthetic', True, id=1)
        self.bob = Account('Bob', 'synthetic', True, id=2)

    def select(self, account):
        self.context._active_account = account
        self.context.active_account_changed.emit(account)

    def test_old_callbacks_rejected_and_new_account_retries_as_soon_as_worker_finishes(self):
        self.select(self.alice)
        self.home._refresh_activity_feed(show_loading=True)
        old = self.workers.pending[HOME_WORKER_ACTIVITY]
        self.home._on_activity_entry_ready(entry('Alice'))
        self.select(self.bob)
        self.assertEqual(self.home._activity_entries, [])
        self.assertEqual(self.home._activity_cache, [])
        self.assertEqual(self.home._displayed_account_label.text(), 'Account: Bob')
        self.home._refresh_activity_feed(show_loading=True)
        self.assertIsNone(self.home._activity_last_attempt)
        self.assertTrue(self.home._activity_refresh_pending)
        with patch.object(self.home, '_on_activity_feed_failed') as failed:
            old.partial_result.emit(entry('Alice'))
            old.finished_ok.emit(ActivityFeedResult([entry('Alice')], []))
            old.failed.emit('Alice error')
            self.assertEqual(self.home._activity_entries, [])
            self.assertEqual(self.home._activity_cache, [])
            failed.assert_not_called()
        self.workers.finish(HOME_WORKER_ACTIVITY)
        QTest.qWait(10)
        new = self.workers.pending[HOME_WORKER_ACTIVITY]
        self.assertIsNot(new, old)
        self.assertEqual(new._args[0].id, self.bob.id)
        new.finished_ok.emit(ActivityFeedResult([entry('Bob')], []))
        self.assertEqual([e.username for e in self.home._activity_cache], ['Bob'])

    def test_refresh_during_same_account_fetch_does_not_queue_a_duplicate(self):
        self.select(self.alice)
        self.home._refresh_activity_feed(show_loading=True)
        first = self.workers.pending[HOME_WORKER_ACTIVITY]
        # e.g. the periodic timer firing while the first fetch is in flight
        self.home._refresh_activity_feed(show_loading=False)
        self.assertFalse(self.home._activity_refresh_pending)
        self.workers.finish(HOME_WORKER_ACTIVITY)
        QTest.qWait(10)
        self.assertNotIn(HOME_WORKER_ACTIVITY, self.workers.pending)
        self.assertEqual(self.workers.all.count(first), 1)

    def test_logout_drops_delayed_activity_and_photo_results_and_pending_retry(self):
        self.select(self.alice)
        generation = self.home._account_generation
        self.home._refresh_activity_feed(show_loading=True)
        old = self.workers.pending[HOME_WORKER_ACTIVITY]
        self.select(None)
        with patch.object(self.home, '_on_photo_ready') as photo, patch.object(self.home, '_on_activity_feed_failed') as failed:
            self.home._on_photo_ready_guarded(None, generation, self.alice.id)
            old.partial_result.emit(entry('Alice'))
            old.finished_ok.emit(ActivityFeedResult([entry('Alice')], []))
            old.failed.emit('late error')
            photo.assert_not_called()
            failed.assert_not_called()
        self.workers.finish(HOME_WORKER_ACTIVITY)
        QTest.qWait(10)
        self.assertEqual(self.home._activity_cache, [])
        self.assertNotIn(HOME_WORKER_ACTIVITY, self.workers.pending)

    def test_photo_and_profile_callbacks_cannot_update_other_account(self):
        self.select(self.alice)
        generation = self.home._account_generation
        self.select(self.bob)
        with patch.object(self.home, '_on_photo_ready') as photo, patch.object(self.home, '_on_profile_sync_done') as done, patch.object(self.home, '_on_profile_sync_failed') as failed:
            self.home._on_photo_ready_guarded(None, generation, self.alice.id)
            self.home._on_profile_sync_done_guarded(True, generation, self.alice.id)
            self.home._on_profile_sync_failed_guarded('old failure', generation, self.alice.id)
            photo.assert_not_called()
            done.assert_not_called()
            failed.assert_not_called()
            self.home._on_photo_ready_guarded(None, self.home._account_generation, self.bob.id)
            photo.assert_called_once_with(None)

    def test_home_settings_and_both_explorers_share_one_sync_slot(self):
        self.select(self.alice)
        worker = self.home._start_profile_sync(self.alice)
        self.assertIsNotNone(worker)
        self.assertTrue(worker.cancellable)
        self.assertEqual(jobs.active_job(), jobs.JOB_SYNC_PROFILE)
        settings = SettingsPage(self.context)
        self.addCleanup(settings.close)
        from retrocheevos.gui.pages.explorer_page import ExplorerPage
        explorer = ExplorerPage(self.context)
        self.addCleanup(explorer.close)
        before = len(self.workers.all)
        with patch('retrocheevos.gui.pages.settings_page.QMessageBox.warning') as busy:
            settings._on_sync_profile()
            explorer._on_sync_everything()
            self.home._explorer_page._on_sync_everything()
        self.assertEqual(busy.call_count, 3)
        self.assertEqual(len(self.workers.all), before)
        worker.finished.emit()
        self.assertIsNone(jobs.active_job())
        token = jobs.try_acquire(jobs.JOB_SYNC_EVERYTHING)
        self.assertIsNotNone(token)
        self.assertIsNone(self.home._start_profile_sync(self.bob))
        jobs.release(token)

    def test_home_releases_slot_when_worker_setup_fails(self):
        self.select(self.alice)
        with patch('retrocheevos.services.session_service.build_api_client', side_effect=RuntimeError('setup')):
            with self.assertRaises(RuntimeError):
                self.home._start_profile_sync(self.alice)
        self.assertIsNone(jobs.active_job())
