"""Live Home progress updates without flicker or cross-account results."""

import time
import unittest
from datetime import datetime, timezone
from threading import Event
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from retrocheevos.models.account import Account
from retrocheevos.models.now_playing import LiveAchievement, NowPlayingSnapshot
from retrocheevos.services import now_playing_service
from retrocheevos.widgets.now_playing_panel import NowPlayingPanel, REFRESH_INTERVAL_MS, MAX_RETRY_INTERVAL_MS

_app = QApplication.instance() or QApplication([])


class NowPlayingPanelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.panel = NowPlayingPanel()
        self.addCleanup(self.panel.close)
        self.account = Account('Tester', 'fake', True, id=1)
        self.panel.set_account(self.account)
        self.panel._worker_generation = self.panel._generation
        self.now = datetime.now(timezone.utc)

    def _snapshot(self, unlocked: bool = False) -> NowPlayingSnapshot:
        return NowPlayingSnapshot(
            1, 100, 'Current game', active=True, source='local', checked_at=self.now,
            achievements=[
                LiveAchievement(1, 'First', 'Description', 5, self.now, True),
                LiveAchievement(2, 'Second', 'Do something', 10, self.now if unlocked else None),
            ],
        )

    def test_progress_unlock_banner_and_unchanged_rows(self) -> None:
        self.panel._on_result(self._snapshot())
        self.assertEqual(self.panel._progress.value(), 500)
        self.assertEqual(self.panel._locked.count(), 1)
        self.assertEqual(self.panel._unlocked.count(), 1)
        original_row = self.panel._locked.item(0)
        self.panel._on_result(self._snapshot())
        self.assertIs(self.panel._locked.item(0), original_row)
        self.panel._on_result(self._snapshot(unlocked=True))
        self.assertEqual(self.panel._progress.value(), 1000)
        self.assertEqual(self.panel._unlocked.count(), 2)
        self.assertIn('Second', self.panel._unlock_banner.text())

    def test_stale_account_result_is_ignored_and_logout_clears_data(self) -> None:
        self.panel._on_result(self._snapshot())
        self.panel.set_account(Account('Other', 'fake2', True, id=2))
        self.panel._on_result(self._snapshot())
        self.assertNotIn('Current game', self.panel._title.text())
        self.assertEqual(self.panel._unlocked.count(), 0)
        self.panel.set_account(None)
        self.assertIn('Select an account', self.panel._title.text())
        self.assertFalse(self.panel._refresh_button.isEnabled())

    def test_error_backoff_is_bounded_and_success_recovers(self) -> None:
        for _ in range(10):
            self.panel._on_error('rate limited')
        self.assertEqual(self.panel._interval, MAX_RETRY_INTERVAL_MS)
        self.panel._on_result(self._snapshot())
        self.assertEqual(self.panel._interval, REFRESH_INTERVAL_MS)

    def test_background_refresh_does_not_duplicate_requests_and_stops_when_hidden(self) -> None:
        release = Event()
        def fetch(_account, **_kwargs):
            release.wait(2)
            return self._snapshot()
        def wait_for(predicate):
            deadline = time.monotonic() + 5
            while not predicate():
                if time.monotonic() > deadline:
                    self.fail('background refresh timed out')
                QTest.qWait(5)
        with patch.object(now_playing_service, 'refresh_now_playing', side_effect=fetch) as fetcher:
            self.panel.show()
            try:
                wait_for(lambda: fetcher.call_count == 1)
                self.panel.refresh_progress()
                self.panel.refresh_progress()
                self.assertEqual(fetcher.call_count, 1)
                release.set()
                wait_for(lambda: self.panel._worker is None)
                self.panel.hide()
                self.assertFalse(self.panel._timer.isActive())
                self.panel.refresh_progress(force=True)
                self.assertEqual(fetcher.call_count, 1)
            finally:
                release.set()
                wait_for(lambda: self.panel._worker is None)
                self.panel.hide()
