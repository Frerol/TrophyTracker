"""Streaming reuses cards and partial/failed refreshes retain last-good data."""

import unittest
from dataclasses import replace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QVBoxLayout, QWidget

from retrocheevos.gui.pages.home_page import HomePage, ACTIVITY_REFRESH_INTERVAL_MS
from retrocheevos.models.activity_feed import ActivityEntry, ActivityFeedResult

_app = QApplication.instance() or QApplication([])


def entry(username):
    return ActivityEntry(username, False, None, 'Playing', None, 'Game', 'NES', None, 1, 10, 60)


class FeedView:
    _clear_activity_feed = HomePage._clear_activity_feed
    _render_activity_entries = HomePage._render_activity_entries
    _render_activity_entries_now = HomePage._render_activity_entries_now
    _on_activity_entry_ready = HomePage._on_activity_entry_ready
    _on_activity_feed_ready = HomePage._on_activity_feed_ready
    _on_activity_feed_failed = HomePage._on_activity_feed_failed
    _back_off_activity_refresh = HomePage._back_off_activity_refresh
    _reset_activity_refresh_interval = HomePage._reset_activity_refresh_interval

    def __init__(self):
        self._activity_feed_container = QWidget()
        self._activity_feed_layout = QVBoxLayout(self._activity_feed_container)
        self._recent_activity_group = QGroupBox('Recent Activity')
        self._activity_refresh_timer = QTimer()
        self._activity_retry_interval_ms = ACTIVITY_REFRESH_INTERVAL_MS
        self._activity_cards = {}
        self._activity_entries = []
        self._activity_cache = []
        self._stream_activity_entries = True


class ActivityRenderingTests(unittest.TestCase):
    def setUp(self):
        self.view = FeedView()
        self.addCleanup(self.view._activity_feed_container.close)
        self.addCleanup(self.view._recent_activity_group.close)

    def test_streaming_and_final_sort_reuse_unchanged_cards(self):
        view = self.view
        view._activity_feed_layout.addWidget(QLabel('Loading…'))
        first = entry('first')
        view._on_activity_entry_ready(first)
        original = view._activity_cards['first'][1]
        for index in range(30):
            view._on_activity_entry_ready(entry(f'user{index}'))
            self.assertIs(view._activity_cards['first'][1], original)
        self.assertEqual(view._activity_feed_layout.count(), 31)
        view._render_activity_entries(list(reversed(view._activity_entries)))
        self.assertIs(view._activity_cards['first'][1], original)
        self.assertIs(view._activity_feed_layout.itemAt(30).widget(), original)
        changed = replace(first, status_text='New status')
        view._render_activity_entries([changed])
        self.assertIsNot(view._activity_cards['first'][1], original)
        self.assertEqual(view._activity_feed_layout.count(), 1)

    def test_partial_refresh_keeps_failed_users_and_backs_off(self):
        view = self.view
        previous = entry('offline')
        view._activity_cache = [previous, entry('no_longer_followed')]
        view._on_activity_feed_ready(ActivityFeedResult([entry('online')], ['offline']))
        self.assertEqual({e.username for e in view._activity_cache}, {'offline', 'online'})
        self.assertIn('partially updated', view._recent_activity_group.title())
        self.assertEqual(view._activity_retry_interval_ms, ACTIVITY_REFRESH_INTERVAL_MS * 2)
        view._on_activity_feed_ready(ActivityFeedResult([entry('online')], []))
        self.assertEqual(view._activity_retry_interval_ms, ACTIVITY_REFRESH_INTERVAL_MS)
        self.assertEqual(view._recent_activity_group.title(), 'Recent Activity')

    def test_failed_progress_lookup_retains_last_known_progress_for_same_game(self):
        view = self.view
        cached = entry('friend')
        view._activity_cache = [cached]
        partial = replace(cached, progress_unavailable=True, achievements_unlocked=None,
                          achievements_total=None, playtime_seconds=None)
        view._on_activity_feed_ready(ActivityFeedResult([partial], ['friend']))
        self.assertEqual(view._activity_cache[0].achievements_unlocked, 1)
        self.assertTrue(view._activity_cache[0].progress_unavailable)
        changed_game = replace(partial, game_title='Different game')
        view._on_activity_feed_ready(ActivityFeedResult([changed_game], ['friend']))
        self.assertIsNone(view._activity_cache[0].achievements_unlocked)

    def test_missing_follow_list_retains_cached_users(self):
        view = self.view
        view._activity_cache = [entry('friend')]
        view._on_activity_feed_ready(ActivityFeedResult([entry('self')], [], True))
        self.assertEqual({e.username for e in view._activity_cache}, {'self', 'friend'})

    def test_failed_silent_refresh_keeps_existing_cards(self):
        view = self.view
        cached = entry('cached')
        view._activity_cache = [cached]
        view._render_activity_entries([cached])
        original = view._activity_cards['cached'][1]
        view._activity_entries = []
        view._on_activity_feed_failed('rate limited')
        self.assertIs(view._activity_cards['cached'][1], original)
        self.assertEqual(view._activity_entries, [cached])
