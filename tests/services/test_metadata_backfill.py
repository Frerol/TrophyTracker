"""Successful empty metadata is cached separately; failures, expiry and force retry."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from retrocheevos.api.games import RawGame, RawGameProgression
from retrocheevos.database import connection as db
from retrocheevos.database import migrations
from retrocheevos.database.repositories.game_repository import GameRepository, EMPTY_METADATA_TTL
from retrocheevos.services import sync_service as sync
from retrocheevos.utils.cancellation import OperationCancelled
from retrocheevos.utils.enums import MetadataKind, MetadataFetchOutcome


class MetadataBackfillTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'metadata.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', side_effect=lambda database_path=None: create(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        migrations.initialize_database(self.path).close()
        with db.get_connection() as conn:
            conn.execute("INSERT INTO consoles(id, name) VALUES(1, 'NES')")
            conn.executemany('INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, 1, 1)',
                             [(key, f'Game {key}') for key in range(1, 4)])
        self.client = Mock()
        for patcher in (
            patch.object(sync, 'GamesClient', return_value=self.client),
            patch.object(sync.library_service, 'rematch_unmatched_roms', return_value=0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def expire(self, kind):
        with db.get_connection() as conn:
            conn.execute('UPDATE game_metadata_fetches SET checked_at = ? WHERE metadata_kind = ?',
                         ((datetime.now() - EMPTY_METADATA_TTL - timedelta(seconds=1)).isoformat(), kind.value))

    def test_hash_backfill_skips_empty_retries_failures_and_refreshes_expired(self):
        failed = True

        def hashes(game_id):
            if game_id == 2 and failed:
                raise RuntimeError('temporary failure')
            return ['ABC'] if game_id == 3 else []

        self.client.get_game_hashes.side_effect = hashes
        self.assertEqual(sync.sync_all_game_hashes(None), 1)
        self.assertEqual(self.client.get_game_hashes.call_count, 3)
        self.client.get_game_hashes.reset_mock()
        failed = False
        self.assertEqual(sync.sync_all_game_hashes(None), 0)
        self.client.get_game_hashes.assert_called_once_with(2)
        self.client.get_game_hashes.reset_mock()
        sync.sync_all_game_hashes(None)
        self.client.get_game_hashes.assert_not_called()
        self.expire(MetadataKind.HASHES)
        sync.sync_all_game_hashes(None)
        self.assertEqual([call.args[0] for call in self.client.get_game_hashes.call_args_list], [1, 2])
        self.client.get_game_hashes.reset_mock()
        sync.sync_all_game_hashes(None, force_refresh=True)
        self.assertEqual(self.client.get_game_hashes.call_count, 3)
        with db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT hash FROM game_hashes WHERE game_id=3').fetchone()[0], 'abc')

    def test_median_backfill_remembers_unknown_preserves_zero_and_retries_failure(self):
        failed = True

        def median(game_id):
            if game_id == 2 and failed:
                raise RuntimeError('temporary failure')
            return SimpleNamespace(median_time_to_beat_hardcore_seconds=0 if game_id == 3 else None,
                                   times_used_in_hardcore_beat_median=0)

        self.client.get_median_time_to_beat_hardcore.side_effect = median
        self.assertEqual(sync.sync_median_times(None), 1)
        self.client.get_median_time_to_beat_hardcore.reset_mock()
        failed = False
        self.assertEqual(sync.sync_median_times(None), 0)
        self.client.get_median_time_to_beat_hardcore.assert_called_once_with(2)
        self.client.get_median_time_to_beat_hardcore.reset_mock()
        sync.sync_median_times(None)
        self.client.get_median_time_to_beat_hardcore.assert_not_called()
        with db.get_connection() as conn:
            repository = GameRepository(conn)
            self.assertIsNone(repository.get_by_id(1).median_time_to_beat_hardcore_seconds)
            self.assertEqual(repository.get_by_id(3).median_time_to_beat_hardcore_seconds, 0)
        self.expire(MetadataKind.MEDIAN_TIME)
        sync.sync_median_times(None)
        self.assertEqual([call.args[0] for call in self.client.get_median_time_to_beat_hardcore.call_args_list], [1, 2])
        self.client.get_median_time_to_beat_hardcore.reset_mock()
        sync.sync_median_times(None, force_refresh=True)
        self.assertEqual(self.client.get_median_time_to_beat_hardcore.call_count, 3)

    def test_failed_forced_refresh_preserves_values_and_is_retryable(self):
        self.client.get_game_hashes.return_value = ['abc']
        sync.sync_all_game_hashes(None)
        self.client.get_game_hashes.side_effect = RuntimeError('offline')
        sync.sync_all_game_hashes(None, force_refresh=True)
        with db.get_connection() as conn:
            self.assertEqual(GameRepository(conn).find_game_id_by_hash('abc'), 1)
            self.assertEqual(GameRepository(conn).list_ids_missing_hashes(), [1, 2, 3])
        self.client.get_game_hashes.side_effect = None
        self.client.get_game_hashes.return_value = []
        self.client.get_game_hashes.reset_mock()
        sync.sync_all_game_hashes(None)
        self.assertEqual(self.client.get_game_hashes.call_count, 3)
        with db.get_connection() as conn:
            self.assertIsNone(GameRepository(conn).find_game_id_by_hash('abc'))

    def test_full_details_also_remembers_both_empty_responses(self):
        self.client.get_game_extended.side_effect = lambda game_id: (
            RawGame(game_id, f'Game {game_id}', 1, None, 1), [],
        )
        self.client.get_median_time_to_beat_hardcore.side_effect = lambda game_id: RawGameProgression(game_id, None, None)
        self.client.get_game_hashes.return_value = []
        self.assertEqual(sync.sync_all_game_hashes(None, full_details=True), 0)
        self.assertEqual(self.client.get_game_extended.call_count, 3)
        self.client.get_game_extended.reset_mock()
        sync.sync_all_game_hashes(None, full_details=True)
        self.client.get_game_extended.assert_not_called()
        with db.get_connection() as conn:
            self.assertEqual(GameRepository(conn).list_ids_missing_median_time(), [])

    def test_failed_forced_median_refresh_keeps_value_and_retries(self):
        self.client.get_median_time_to_beat_hardcore.return_value = RawGameProgression(1, 600, 5)
        sync.sync_median_times(None)
        self.client.get_median_time_to_beat_hardcore.side_effect = RuntimeError('offline')
        sync.sync_median_times(None, force_refresh=True)
        with db.get_connection() as conn:
            self.assertEqual(GameRepository(conn).get_by_id(1).median_time_to_beat_hardcore_seconds, 600)
            self.assertEqual(GameRepository(conn).list_ids_missing_median_time(), [1, 2, 3])

    def test_selection_preserves_installed_priority(self):
        with db.get_connection() as conn:
            conn.execute("INSERT INTO accounts(id,username,api_key) VALUES(1,'test','unused')")
            conn.execute("INSERT INTO installed_roms(account_id,game_id,file_path,hash,console_id) VALUES(1,3,'/test.nes','',1)")
            repository = GameRepository(conn)
            self.assertEqual(repository.list_ids_missing_hashes(), [3, 1, 2])
            self.assertEqual(repository.list_ids_missing_median_time(), [3, 1, 2])

    def test_cancellation_does_not_record_a_successful_empty_response(self):
        for run, method in ((sync.sync_all_game_hashes, self.client.get_game_hashes),
                            (sync.sync_median_times, self.client.get_median_time_to_beat_hardcore)):
            method.side_effect = OperationCancelled()
            with self.assertRaises(OperationCancelled):
                run(None)
        with db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM game_metadata_fetches').fetchone()[0], 0)

    def test_metadata_marker_and_value_roll_back_together(self):
        with self.assertRaises(RuntimeError):
            with db.get_connection() as conn:
                repository = GameRepository(conn)
                repository.replace_hashes(1, ['abc'])
                repository.record_metadata_fetch(1, MetadataKind.HASHES, MetadataFetchOutcome.VALUE)
                raise RuntimeError('injected failure before commit')
        with db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM game_hashes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM game_metadata_fetches').fetchone()[0], 0)

    def test_expiry_boundary_and_independent_metadata_clocks(self):
        now = datetime(2026, 11, 20, 12)
        with db.get_connection() as conn:
            repository = GameRepository(conn)
            repository.record_metadata_fetch(1, MetadataKind.HASHES, MetadataFetchOutcome.EMPTY, now)
            repository.record_metadata_fetch(2, MetadataKind.HASHES, MetadataFetchOutcome.EMPTY, now - EMPTY_METADATA_TTL)
            self.assertEqual(repository.list_ids_missing_hashes(now=now), [2, 3])
            self.assertEqual(repository.list_ids_missing_median_time(now=now), [1, 2, 3])
            self.assertEqual(repository.list_ids_missing_hashes(force_refresh=True, now=now), [1, 2, 3])

    def test_upgrade_adds_fetch_tracking_without_inventing_success_for_old_rows(self):
        old_path = self.path.with_name('old.db')
        older = [migration for migration in migrations.MIGRATIONS if migration[0] <= 27]
        with patch.object(migrations, 'MIGRATIONS', older):
            conn = migrations.initialize_database(old_path)
        conn.execute("INSERT INTO consoles(id, name) VALUES(1, 'NES')")
        conn.execute("INSERT INTO games(id,title,console_id,has_achievements) VALUES(1,'Old',1,1)")
        conn.commit()
        migrations.apply_migrations(conn)
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM game_metadata_fetches').fetchone()[0], 0)
            self.assertEqual(GameRepository(conn).list_ids_missing_hashes(), [1])
        finally:
            conn.close()
