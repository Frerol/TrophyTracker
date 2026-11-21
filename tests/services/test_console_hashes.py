"""Per-console catalog hashes for automatic matching (R22)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import retrocheevos.database.connection as db
from retrocheevos.api.games import GamesClient
from retrocheevos.database.migrations import initialize_database
from retrocheevos.services import library_service, sync_service
from retrocheevos.utils.cancellation import OperationCancelled


def game_list(console_id):
    return {
        12: [
            {"ID": 11244, "Title": "Metal Gear Solid", "ImageIcon": "/Images/1.png",
             "NumAchievements": 40, "Hashes": ["A0F6984304D16D0995364728DD175BE8", "x2"]},
            {"ID": 11245, "Title": "No Hash Game", "NumAchievements": 10, "Hashes": []},
        ],
        3: [{"ID": 1, "Title": "Super Metroid", "NumAchievements": 40, "Hashes": ["snes1"]}],
    }[console_id]


class ApiTests(unittest.TestCase):
    def test_game_list_with_hashes_is_one_request_per_console(self):
        client = MagicMock()
        client.get.side_effect = lambda _endpoint, params: game_list(params["i"])
        rows = GamesClient(client).list_games_with_hashes(12)
        client.get.assert_called_once_with("API_GetGameList.php", {"i": 12, "f": 1, "h": 1})
        self.assertEqual([(game.id, game.console_id) for game, _ in rows], [(11244, 12), (11245, 12)])
        self.assertEqual(rows[0][1], ["A0F6984304D16D0995364728DD175BE8", "x2"])
        self.assertEqual(rows[1][1], [])


class ConsoleHashSyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.path = self.tmp / 'hashes.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.path).close()
        with db.get_connection(self.path) as c:
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'alice', '', 1)")
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(2, 'bob', '', 0)")
            for console_id in (3, 5, 12, 19):
                c.execute("INSERT OR IGNORE INTO consoles(id, name) VALUES(?, ?)", (console_id, f'Console {console_id}'))
            for name, console, rom_hash, account in (
                ('mgs1.chd', 12, 'a0f6984304d16d0995364728dd175be8', 1),
                ('wii.rvz', 19, '', 1),
                ('hack.sfc', 3, 'nomatch', 1),
                ('bob.gba', 5, 'bobhash', 2),
            ):
                path = self.tmp / name
                path.write_bytes(b'x')
                c.execute("INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id)"
                          " VALUES(NULL, ?, ?, ?, ?)", (str(path), rom_hash, console, account))
        self.client = MagicMock()
        self.client.get.side_effect = lambda _endpoint, params: game_list(params["i"])

    def test_consoles_needing_hashes_skips_unhashed_files_and_other_accounts(self):
        self.assertEqual(library_service.consoles_needing_hashes(), [3, 12])

    def test_sync_stores_games_and_hashes_then_matches(self):
        progress = []
        result = sync_service.sync_console_hashes(
            self.client, [12], progress_callback=lambda done, total: progress.append((done, total)),
        )
        self.assertEqual((result.consoles, result.games, result.hashes, result.matched), (1, 2, 2, 1))
        self.assertEqual(progress, [(1, 1)])
        roms = {Path(r.file_path).name: r for r in library_service.list_installed_roms()}
        self.assertEqual(roms['mgs1.chd'].game_id, 11244)
        self.assertFalse(roms['mgs1.chd'].manual_match)
        self.assertIsNone(roms['hack.sfc'].game_id)
        self.assertEqual(library_service.consoles_needing_hashes(), [3])
        # Re-running replaces, not duplicates, the hash rows.
        sync_service.sync_console_hashes(self.client, [12])
        with db.get_connection(self.path) as c:
            count = c.execute("SELECT COUNT(*) FROM game_hashes WHERE game_id = 11244").fetchone()[0]
        self.assertEqual(count, 2)

    def test_cancellation_keeps_fetched_consoles_and_still_matches(self):
        def should_cancel():
            # Cancel once the first console's hashes are stored.
            with db.get_connection(self.path) as c:
                return c.execute("SELECT COUNT(*) FROM game_hashes").fetchone()[0] > 0

        with self.assertRaises(OperationCancelled):
            sync_service.sync_console_hashes(self.client, [12, 3], should_cancel=should_cancel)
        roms = {Path(r.file_path).name: r for r in library_service.list_installed_roms()}
        self.assertEqual(roms['mgs1.chd'].game_id, 11244)
        self.assertEqual(library_service.consoles_needing_hashes(), [3])


if __name__ == '__main__':
    unittest.main()
