"""ROM hash matching must ignore case.

RetroAchievements' API is inconsistent about it: in one synced catalog 176 of
13327 hash rows came back uppercase, across 137 games — Pokémon Snap,
Terranigma, Jet Force Gemini. Every hasher this app uses (RAHasher, `psp_hash`,
the whole-file MD5 fallback) prints lowercase, and SQLite compares TEXT
case-sensitively, so those games were unmatchable by a correctly-hashed ROM.

The symptom was Pokémon Snap sitting in "Unmatched ROMs" with the hash
FC3C9329B7CDD67CF7650ABF63B9A580 in the catalog and fc3c9329b7cdd67cf7650abf63b9a580
on the file: the same 32 characters, and no match.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import retrocheevos.database.connection as connection_module
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.models.console import Console
from retrocheevos.models.game import Game
from retrocheevos.utils.enums import GameType

CONSOLE_ID = 2
SNAP_UPPER = "FC3C9329B7CDD67CF7650ABF63B9A580"
SNAP_LOWER = SNAP_UPPER.lower()


class GameHashCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        from retrocheevos.database.migrations import initialize_database

        self.path = Path(tempfile.mkdtemp()) / "hashes.db"
        real_create = connection_module.create_connection
        patcher = patch.object(
            connection_module,
            "create_connection",
            lambda database_path=None: real_create(self.path),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.path).close()

        with connection_module.get_connection() as conn:
            ConsoleRepository(conn).upsert(Console(id=CONSOLE_ID, name="Nintendo 64"))
        with connection_module.get_connection() as conn:
            GameRepository(conn).upsert_game(
                Game(
                    id=10155, title="Pokémon Snap", console_id=CONSOLE_ID,
                    has_achievements=True, image_path="/x.png",
                    game_type=GameType.RETAIL, retroachievements_url="https://x",
                )
            )

    def test_uppercase_api_hash_matches_a_lowercase_rom_hash(self) -> None:
        with connection_module.get_connection() as conn:
            GameRepository(conn).replace_hashes(10155, [SNAP_UPPER])

        with connection_module.get_connection() as conn:
            self.assertEqual(
                GameRepository(conn).find_game_id_by_hash(SNAP_LOWER), 10155
            )

    def test_lowercase_api_hash_still_matches(self) -> None:
        with connection_module.get_connection() as conn:
            GameRepository(conn).replace_hashes(10155, [SNAP_LOWER])

        with connection_module.get_connection() as conn:
            self.assertEqual(
                GameRepository(conn).find_game_id_by_hash(SNAP_LOWER), 10155
            )

    def test_an_uppercase_rom_hash_matches_too(self) -> None:
        """Belt and braces — a future hasher printing uppercase must not
        reintroduce the bug from the other side.
        """
        with connection_module.get_connection() as conn:
            GameRepository(conn).replace_hashes(10155, [SNAP_LOWER])

        with connection_module.get_connection() as conn:
            self.assertEqual(
                GameRepository(conn).find_game_id_by_hash(SNAP_UPPER), 10155
            )

    def test_hashes_are_stored_lowercase(self) -> None:
        """Normalizing on the way in is what keeps `idx_game_hashes_hash`
        usable — the LOWER() in the query is only a fallback for old rows.
        """
        with connection_module.get_connection() as conn:
            GameRepository(conn).replace_hashes(10155, [SNAP_UPPER])

        with connection_module.get_connection() as conn:
            stored = conn.execute(
                "SELECT hash FROM game_hashes WHERE game_id = 10155"
            ).fetchone()[0]
        self.assertEqual(stored, SNAP_LOWER)

    def test_a_genuinely_different_hash_still_misses(self) -> None:
        with connection_module.get_connection() as conn:
            GameRepository(conn).replace_hashes(10155, [SNAP_UPPER])

        with connection_module.get_connection() as conn:
            self.assertIsNone(
                GameRepository(conn).find_game_id_by_hash("0" * 32)
            )

    def test_migration_23_lowercases_rows_written_before_the_fix(self) -> None:
        """Rows already in the database bypassed `replace_hashes` — they were
        inserted by the version that stored whatever the API sent.
        """
        with connection_module.get_connection() as conn:
            conn.execute(
                "INSERT INTO game_hashes (game_id, hash) VALUES (?, ?)",
                (10155, SNAP_UPPER),
            )

        from retrocheevos.database.migrations import MIGRATIONS, apply_migrations

        with connection_module.get_connection() as conn:
            conn.execute("PRAGMA user_version = 22")
        with connection_module.get_connection() as conn:
            # Replay only the historical migration on this latest-schema fixture.
            with patch('retrocheevos.database.migrations.MIGRATIONS', [
                entry for entry in MIGRATIONS if entry[0] <= 23
            ]):
                apply_migrations(conn)

        with connection_module.get_connection() as conn:
            rows = [
                r[0]
                for r in conn.execute("SELECT hash FROM game_hashes WHERE game_id = 10155")
            ]
        self.assertTrue(rows)
        self.assertTrue(all(h == h.lower() for h in rows), rows)


if __name__ == "__main__":
    unittest.main()
