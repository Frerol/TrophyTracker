"""Live game progress is current, account-scoped and safe against account removal."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import retrocheevos.database.connection as db
from retrocheevos.api.achievements import AchievementProgressClient, RawLiveAchievement, RawLiveGameProgress
from retrocheevos.api.profile import RawUserSummary
from retrocheevos.database.migrations import initialize_database
from retrocheevos.database.repositories.game_completion_repository import GameCompletionRepository
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.models.game import Game
from retrocheevos.services import credential_store, now_playing_service as live, play_session_service, session_service


class NowPlayingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'test.db'
        real_create = db.create_connection
        for patcher in (
            patch.object(db, 'create_connection', lambda database_path=None: real_create(self.database)),
            patch.object(credential_store, 'set_key', return_value=False),
            patch.object(credential_store, 'get_key', return_value=None),
            patch.object(play_session_service, 'get_running_session', return_value=None),
            patch.object(live.ProfileClient, 'get_user_summary', return_value=RawUserSummary(None, None, None, None, None, None, None)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        initialize_database(self.database).close()
        self.account = session_service.add_account('Tester', 'fake')
        with db.get_connection() as connection:
            connection.execute("INSERT INTO consoles (id, name) VALUES (19, 'Wii')")
            GameRepository(connection).upsert_game(Game(100, 'Game', 19, True))
        self.now = datetime.now(timezone.utc)
        self.progress = RawLiveGameProgress(100, 'Game', [
            RawLiveAchievement(1, 'First', 'First achievement', 5, self.now, True),
            RawLiveAchievement(2, 'Second', 'Second achievement', 10, None, False),
        ])

    def test_locally_launched_game_updates_cached_counts(self) -> None:
        with patch.object(play_session_service, 'get_running_session', return_value=play_session_service.PlaySession(100, 'Game', MagicMock())), patch.object(AchievementProgressClient, 'get_live_game_progress', return_value=self.progress):
            snapshot = live.refresh_now_playing(self.account)
        self.assertTrue(snapshot.active)
        self.assertEqual(snapshot.source, 'local')
        with db.get_connection() as connection:
            completion = GameCompletionRepository(connection).get(self.account.id, 100)
            self.assertEqual(completion.percent_complete, 50)
            self.assertEqual(completion.achievements_unlocked, 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM user_achievements').fetchone()[0], 1)

    def test_recent_ra_game_can_be_detected_without_a_local_launch(self) -> None:
        summary = RawUserSummary(None, 'Playing level 2', self.now.replace(tzinfo=None), 100, 'Game', 'Wii', None)
        with patch.object(live.ProfileClient, 'get_user_summary', return_value=summary), patch.object(AchievementProgressClient, 'get_live_game_progress', return_value=self.progress):
            snapshot = live.refresh_now_playing(self.account)
        self.assertTrue(snapshot.active)
        self.assertEqual(snapshot.source, 'retroachievements')
        self.assertEqual(snapshot.presence, 'Playing level 2')

    def test_stale_last_game_is_not_presented_as_current(self) -> None:
        summary = RawUserSummary(None, 'Old presence', self.now - timedelta(days=1), 100, 'Game', 'Wii', None)
        with patch.object(live.ProfileClient, 'get_user_summary', return_value=summary), patch.object(AchievementProgressClient, 'get_live_game_progress') as progress:
            snapshot = live.refresh_now_playing(self.account)
        self.assertFalse(snapshot.active)
        progress.assert_not_called()

    def test_unmatched_local_rom_does_not_show_an_unrelated_ra_game(self) -> None:
        with patch.object(play_session_service, 'get_running_session', return_value=play_session_service.PlaySession(None, 'Local Wii ROM', MagicMock())):
            snapshot = live.refresh_now_playing(self.account)
        self.assertEqual(snapshot.title, 'Local Wii ROM')
        self.assertIsNone(snapshot.game_id)
        self.assertIn('Match this ROM', snapshot.notice)

    def test_newer_ra_activity_detects_game_switched_inside_emulator(self) -> None:
        summary = RawUserSummary(None, 'New game', self.now, 100, 'Game', 'Wii', None)
        local = play_session_service.PlaySession(999, 'Old game', MagicMock(), self.now - timedelta(minutes=5))
        with patch.object(play_session_service, 'get_running_session', return_value=local), patch.object(live.ProfileClient, 'get_user_summary', return_value=summary), patch.object(AchievementProgressClient, 'get_live_game_progress', return_value=self.progress):
            snapshot = live.refresh_now_playing(self.account)
        self.assertEqual(snapshot.game_id, 100)
        self.assertEqual(snapshot.presence, 'New game')

    def test_account_removed_during_request_does_not_receive_progress(self) -> None:
        def remove_account(*_args):
            with db.get_connection() as connection:
                connection.execute('DELETE FROM accounts WHERE id = ?', (self.account.id,))
            return self.progress
        with patch.object(play_session_service, 'get_running_session', return_value=play_session_service.PlaySession(100, 'Game', MagicMock())), patch.object(AchievementProgressClient, 'get_live_game_progress', side_effect=remove_account):
            self.assertIsNone(live.refresh_now_playing(self.account))

    def test_cancel_between_requests_avoids_progress_fetch(self) -> None:
        stop = MagicMock(side_effect=[False, True])
        with patch.object(AchievementProgressClient, 'get_live_game_progress') as progress:
            self.assertIsNone(live.refresh_now_playing(self.account, stop_requested=stop))
        progress.assert_not_called()


class LiveProgressParsingTests(unittest.TestCase):
    def test_locked_softcore_and_hardcore_unlocks(self) -> None:
        client = MagicMock()
        client.get.return_value = {'Title': 'Game', 'Achievements': {
            '1': {'Title': 'Locked', 'Description': 'Later', 'Points': 5},
            '2': {'Title': 'Softcore', 'Points': 10, 'DateEarned': '2026-11-19 10:00:00'},
            '3': {'Title': 'Hardcore', 'Points': 15, 'DateEarnedHardcore': '2026-11-19T10:01:00+00:00'},
            '4': {'Title': 'Unofficial', 'Flags': 5},
        }}
        result = AchievementProgressClient(client).get_live_game_progress('Tester', 100)
        self.assertEqual(len(result.achievements), 3)
        self.assertIsNone(result.achievements[0].unlocked_at)
        self.assertFalse(result.achievements[1].hardcore)
        self.assertTrue(result.achievements[2].hardcore)

    def test_local_process_sessions_are_account_scoped_and_end_on_exit(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        with patch.dict(play_session_service._sessions, {}, clear=True):
            play_session_service.record_launch(1, 100, 'Game', process)
            self.assertIsNotNone(play_session_service.get_running_session(1))
            self.assertIsNone(play_session_service.get_running_session(2))
            process.poll.return_value = 0
            self.assertIsNone(play_session_service.get_running_session(1))
