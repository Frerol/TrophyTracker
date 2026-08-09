"""Deleting an account while its sync is running must not crash.

The reported symptom was "Remove Selected crashes with FOREIGN KEY constraint
failed", but the removal itself had already succeeded — the log showed
"Removed account id=3 and its data" 328ms *before* the error. What failed was
a background `sync_event_progress`, still running from an earlier "Sync
Everything", writing a `game_completion` for the id that had just gone.

The window is wide: that loop makes ~237 requests at 0.3s each, so it stays
live for over a minute after the button that started it looks finished.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import retrocheevos.database.connection as connection_module
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.models.console import Console
from retrocheevos.models.game import Game
from retrocheevos.services import session_service, sync_service
from retrocheevos.utils.enums import GameType

EVENTS_CONSOLE_ID = 101
EVENT_COUNT = 5


class AccountRemovedMidSyncTests(unittest.TestCase):
    def setUp(self):
        from retrocheevos.database.migrations import initialize_database

        self.path = Path(tempfile.mkdtemp()) / "sync.db"
        real_create = connection_module.create_connection
        patcher = patch.object(
            connection_module,
            "create_connection",
            lambda database_path=None: real_create(self.path),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        initialize_database(self.path).close()
        sync_service.CATALOG_SYNC_CALL_DELAY_SECONDS = 0.0

        with connection_module.get_connection() as conn:
            ConsoleRepository(conn).upsert(
                Console(id=EVENTS_CONSOLE_ID, name="Events")
            )
        with connection_module.get_connection() as conn:
            repository = GameRepository(conn)
            for game_id in range(1, EVENT_COUNT + 1):
                repository.upsert_game(
                    Game(
                        id=game_id, title=f"Event {game_id}",
                        console_id=EVENTS_CONSOLE_ID, has_achievements=True,
                        image_path="/x.png", game_type=GameType.RETAIL,
                        retroachievements_url="https://x",
                    )
                )
        self.account = session_service.add_account("Tester", "K" * 32)

    def _fake_games(self, remove_at=None):
        account_id = self.account.id
        state = {"calls": 0}

        class FakeGames:
            def __init__(self, client):
                pass

            def list_games_for_console(self, console_id, only_with_achievements=True):
                return []

            def get_user_game_progress(self, username, game_id):
                state["calls"] += 1
                # Removed *during* the request — the case a check placed
                # before the write cannot catch, only handle.
                if remove_at is not None and state["calls"] == remove_at:
                    session_service.remove_account(account_id)
                return SimpleNamespace(achievements_unlocked=1, achievements_total=10)

        return FakeGames

    def _count(self, table):
        with connection_module.get_connection() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_removal_mid_sync_stops_cleanly(self):
        with patch.object(sync_service, "GamesClient", self._fake_games(remove_at=2)):
            sync_service.sync_event_progress(client=None, account=self.account)

        self.assertEqual(self._count("accounts"), 0)
        self.assertEqual(self._count("game_completion"), 0)
        with connection_module.get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_untouched_sync_still_writes_everything(self):
        with patch.object(sync_service, "GamesClient", self._fake_games()):
            sync_service.sync_event_progress(client=None, account=self.account)
        self.assertEqual(self._count("game_completion"), EVENT_COUNT)

    def test_a_real_integrity_error_still_raises(self):
        """The handler must not become a blanket "ignore foreign keys". With
        the account still present, an integrity failure means something else
        and has to keep propagating."""

        def explode(_self, _completion):
            raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

        with patch.object(sync_service, "GamesClient", self._fake_games()):
            with patch.object(GameCompletionRepository, "upsert", explode):
                with self.assertRaises(sqlite3.IntegrityError):
                    sync_service.sync_event_progress(
                        client=None, account=self.account
                    )


if __name__ == "__main__":
    unittest.main()
