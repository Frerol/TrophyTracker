"""Individual activity failures retain other users; global failures propagate."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from retrocheevos.api.exceptions import AuthenticationError, RateLimitError
from retrocheevos.models.account import Account
from retrocheevos.services import activity_feed_service as feed
from retrocheevos.utils.cancellation import OperationCancelled


def summary(last_game_id=None):
    return SimpleNamespace(
        user_pic_path=None, last_game_id=last_game_id,
        rich_presence_msg='Playing', last_seen_at=None,
        last_game_icon_path=None, last_game_title='Game', last_game_console='NES',
    )


class ActivityFeedTests(unittest.TestCase):
    def setUp(self):
        self.account = Account('self', 'unused-test-key', True, id=1)
        self.profile = Mock()
        self.games = Mock()
        self.profile.get_users_i_follow.return_value = [
            SimpleNamespace(username='unavailable'), SimpleNamespace(username='good'),
        ]
        for patcher in (
            patch.object(feed.session_service, 'build_api_client'),
            patch.object(feed, 'ProfileClient', return_value=self.profile),
            patch.object(feed, 'GamesClient', return_value=self.games),
            patch.object(feed.image_service, 'ensure_user_pic_cached', return_value=None),
            patch.object(feed.image_service, 'ensure_activity_icon_cached', return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unavailable_user_does_not_stop_remaining_users_or_stream(self):
        def fetch(username):
            if username == 'unavailable':
                raise RuntimeError('upstream unavailable')
            return summary()
        self.profile.get_user_summary.side_effect = fetch
        streamed = []
        result = feed.get_recent_activity_feed(self.account, streamed.append)
        self.assertEqual([entry.username for entry in result.entries], ['self', 'good'])
        self.assertEqual(streamed, result.entries)
        self.assertTrue(result.partial)
        self.assertEqual(result.failed_usernames, ['unavailable'])

    def test_success_and_complete_failure_are_distinguishable(self):
        self.profile.get_user_summary.return_value = summary()
        self.assertFalse(feed.get_recent_activity_feed(self.account).partial)
        self.profile.get_user_summary.side_effect = RuntimeError('offline')
        result = feed.get_recent_activity_feed(self.account)
        self.assertTrue(result.partial)
        self.assertEqual(result.entries, [])
        self.assertEqual(result.failed_usernames, ['self', 'unavailable', 'good'])

    def test_missing_follow_list_still_returns_self_with_diagnostic(self):
        self.profile.get_users_i_follow.side_effect = RuntimeError('offline')
        self.profile.get_user_summary.return_value = summary()
        result = feed.get_recent_activity_feed(self.account)
        self.assertTrue(result.following_unavailable)
        self.assertTrue(result.partial)
        self.assertEqual([entry.username for entry in result.entries], ['self'])

    def test_optional_progress_failure_keeps_summary_and_marks_partial(self):
        self.profile.get_users_i_follow.return_value = []
        self.profile.get_user_summary.return_value = summary(1)
        self.games.get_user_game_progress.side_effect = RuntimeError('progress unavailable')
        result = feed.get_recent_activity_feed(self.account)
        self.assertEqual(result.entries[0].game_title, 'Game')
        self.assertTrue(result.entries[0].progress_unavailable)
        self.assertEqual(result.failed_usernames, ['self'])

    def test_authentication_rate_limit_and_cancellation_propagate_at_all_stages(self):
        self.profile.get_user_summary.return_value = summary(1)
        self.games.get_user_game_progress.return_value = SimpleNamespace(
            achievements_unlocked=1, achievements_total=10, playtime_seconds=60,
        )
        for method in (self.profile.get_users_i_follow, self.profile.get_user_summary,
                       self.games.get_user_game_progress):
            for error in (AuthenticationError('rejected'), RateLimitError('slow down', 60), OperationCancelled()):
                with self.subTest(method=method, error=type(error)):
                    method.side_effect = error
                    try:
                        with self.assertRaises(type(error)):
                            feed.get_recent_activity_feed(self.account)
                    finally:
                        method.side_effect = None

    def test_cancellation_before_first_request(self):
        with self.assertRaises(OperationCancelled):
            feed.get_recent_activity_feed(self.account, should_cancel=lambda: True)
        self.profile.get_users_i_follow.assert_not_called()
