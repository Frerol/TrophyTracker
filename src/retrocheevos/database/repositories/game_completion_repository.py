"""Data access for the `game_completion` table (models/game_completion.py)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.game_completion import GameCompletion


class GameCompletionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, completion: GameCompletion) -> None:
        self._connection.execute(
            """
            INSERT INTO game_completion (account_id, game_id, percent_complete, last_synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id, game_id) DO UPDATE SET
                percent_complete = excluded.percent_complete,
                last_synced_at = excluded.last_synced_at
            """,
            (
                completion.account_id,
                completion.game_id,
                completion.percent_complete,
                datetime_to_sql(completion.last_synced_at),
            ),
        )

    def get(self, account_id: int, game_id: int) -> Optional[GameCompletion]:
        row = self._connection.execute(
            "SELECT * FROM game_completion WHERE account_id = ? AND game_id = ?",
            (account_id, game_id),
        ).fetchone()
        return self._row_to_completion(row) if row else None

    def get_all_for_account(self, account_id: int) -> dict[int, float]:
        """game_id -> percent_complete, ready for the Explorer to merge into Game Cards."""
        rows = self._connection.execute(
            "SELECT game_id, percent_complete FROM game_completion WHERE account_id = ?",
            (account_id,),
        ).fetchall()
        return {row["game_id"]: row["percent_complete"] for row in rows}

    @staticmethod
    def _row_to_completion(row: sqlite3.Row) -> GameCompletion:
        return GameCompletion(
            account_id=row["account_id"],
            game_id=row["game_id"],
            percent_complete=row["percent_complete"],
            last_synced_at=datetime_from_sql(row["last_synced_at"]),
        )
