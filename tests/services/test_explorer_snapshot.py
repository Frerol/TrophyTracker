"""The worker read retains Core filtering rules and account isolation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrocheevos.database import connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.core.explorer import ExplorerFilters
from retrocheevos.services.explorer_service import get_snapshot


class ExplorerSnapshotTests(unittest.TestCase):
    def test_blocked_completed_list_and_installed_filters(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'explorer.db'
            conn = initialize_database(path)
            conn.executemany("INSERT INTO accounts(id, username, api_key) VALUES(?, ?, '')", [(1, 'one'), (2, 'two')])
            conn.execute("INSERT INTO consoles(id, name) VALUES(1, 'NES')")
            conn.executemany('INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, 1, 1)',
                             [(key, f'Game {key}') for key in range(1, 7)])
            conn.execute("INSERT INTO user_list_definitions(id, account_id, name, slug) VALUES(1, 1, 'Blocked', 'blocked')")
            conn.execute("INSERT INTO user_list_definitions(id, account_id, name) VALUES(2, 1, 'Favorites')")
            conn.executemany("INSERT INTO user_lists(account_id, game_id, list_id, list_type) VALUES(1, ?, ?, 'custom')",
                             [(1, 1), (1, 2), (4, 2), (5, 2)])
            conn.executemany('INSERT INTO game_completion(account_id, game_id, percent_complete, highest_award_kind) VALUES(1, ?, ?, ?)',
                             [(2, 80, 'beaten-hardcore'), (3, 100, None), (4, 25, None)])
            conn.executemany("INSERT INTO installed_roms(account_id, game_id, file_path, hash, console_id) VALUES(?, ?, ?, '', 1)",
                             [(1, 4, '/one'), (2, 5, '/two')])
            conn.commit()
            conn.close()
            create = db.create_connection
            with patch.object(db, 'create_connection', side_effect=lambda database_path=None: create(path)):
                def ids(filters):
                    return [row.game.id for row in get_snapshot(1, filters).results]
                self.assertEqual(ids(ExplorerFilters()), [4, 5, 6])
                self.assertEqual(ids(ExplorerFilters(list_ids_any_of=[2])), [4, 5])
                self.assertEqual(ids(ExplorerFilters(installed_only=True)), [4])
                self.assertEqual(ids(ExplorerFilters(installed_only=True, list_ids_any_of=[2])), [4])
                snapshot = get_snapshot(1, ExplorerFilters(search_text='Game 4'))
                self.assertEqual(snapshot.total_count, 6)
                self.assertEqual(snapshot.installed_game_ids, {4})
                self.assertEqual(snapshot.results[0].percent_complete, 25)
