"""Data behind the rebuilt Home (R19): card counts, badges and award images."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import retrocheevos.database.connection as db
from retrocheevos.api.profile import RawGameProgress
from retrocheevos.core.game_completion import build_game_completions
from retrocheevos.database.migrations import initialize_database
from retrocheevos.database.repositories.game_completion_repository import GameCompletionRepository
from retrocheevos.database.repositories.profile_repository import ProfileRepository
from retrocheevos.models.profile import Badge
from retrocheevos.services import dashboard_service, image_service, profile_service


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.path = self.tmp / 'home.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.path).close()
        with db.get_connection(self.path) as connection:
            connection.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'alice', '', 1)")
            connection.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(2, 'bob', '', 0)")


class CompletionCountTests(DatabaseTestCase):
    def test_profile_completion_keeps_the_combined_count(self):
        completions = build_game_completions(1, [
            RawGameProgress(10, 'Counted', None, 34, 42),
            RawGameProgress(11, 'No total', None, 3, None),
        ])
        self.assertEqual((completions[0].achievements_unlocked, completions[0].achievements_total), (34, 42))
        self.assertEqual((completions[1].achievements_unlocked, completions[1].achievements_total), (None, None))
        self.assertEqual(completions[1].percent_complete, 0.0)

    def test_continue_playing_entries_carry_counts_only_when_known(self):
        with db.get_connection(self.path) as connection:
            connection.execute("INSERT INTO consoles(id, name) VALUES(3, 'SNES')")
            for game_id in (10, 11):
                rom = self.tmp / f'{game_id}.rom'
                rom.write_bytes(b'x')
                connection.execute(
                    "INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, 3, 1)",
                    (game_id, f'Game {game_id}'),
                )
                connection.execute(
                    "INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id) "
                    "VALUES(?, ?, ?, 3, 1)", (game_id, str(rom), f'h{game_id}'),
                )
            repository = GameCompletionRepository(connection)
            for completion in build_game_completions(1, [RawGameProgress(10, 'Game 10', None, 34, 42)]):
                repository.upsert(completion)
            connection.execute(
                "INSERT INTO game_completion(account_id, game_id, percent_complete) VALUES(1, 11, 50)"
            )
        entries = {entry.game.id: entry for entry in dashboard_service.get_continue_playing_games(1)}
        self.assertEqual((entries[10].achievements_unlocked, entries[10].achievements_total), (34, 42))
        self.assertEqual((entries[11].achievements_unlocked, entries[11].achievements_total), (None, None))
        self.assertEqual(entries[11].percent_complete, 50)


class BadgeTests(DatabaseTestCase):
    def test_list_badges_is_account_scoped_and_puts_events_last(self):
        with db.get_connection(self.path) as connection:
            repository = ProfileRepository(connection)
            for name, is_event, account in (
                ('zelda mastery', False, 1), ('Event 2026', True, 1),
                ('Aladdin beaten', False, 1), ("Bob's", False, 2),
            ):
                repository.upsert_badge(Badge(account, name, True, f'/Images/{len(name)}.png', is_event=is_event))
        badges = profile_service.list_badges(1)
        self.assertEqual([b.name for b in badges], ['Aladdin beaten', 'zelda mastery', 'Event 2026'])
        self.assertEqual([b.is_event for b in badges], [False, False, True])
        self.assertTrue(all(b.id is not None and b.owned for b in badges))
        self.assertEqual(profile_service.list_badges(3), [])

    def test_badge_image_cache_downloads_once_and_degrades_to_none(self):
        destination = self.tmp / 'badges' / '012345.png'
        with patch.object(image_service, 'cached_badge_image_path', return_value=destination), \
             patch.object(image_service, 'download_image') as download:
            self.assertIsNone(image_service.ensure_badge_image_cached(None))
            self.assertIsNone(image_service.ensure_badge_image_cached(''))
            download.side_effect = OSError('offline')
            self.assertIsNone(image_service.ensure_badge_image_cached('/Images/012345.png'))
            download.side_effect = lambda _url, path: (path.parent.mkdir(parents=True), path.write_bytes(b'png'))
            self.assertEqual(image_service.ensure_badge_image_cached('/Images/012345.png'), destination)
            self.assertEqual(image_service.ensure_badge_image_cached('/Images/012345.png'), destination)
            self.assertEqual(download.call_count, 2)
            self.assertTrue(download.call_args.args[0].endswith('/Images/012345.png'))


if __name__ == '__main__':
    unittest.main()
