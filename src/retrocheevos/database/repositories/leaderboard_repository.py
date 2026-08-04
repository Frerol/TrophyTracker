"""Data access for the `leaderboard_cache` table (Database.md 6.3)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.leaderboard import LeaderboardEntry
from retrocheevos.utils.enums import LeaderboardScope


class LeaderboardRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, entry: LeaderboardEntry) -> LeaderboardEntry:
        """Replace any cached snapshot for this scope/account with a fresh one."""
        self._connection.execute(
            "DELETE FROM leaderboard_cache WHERE scope = ? AND account_id = ?",
            (entry.scope.value, entry.account_id),
        )
        cursor = self._connection.execute(
            """
            INSERT INTO leaderboard_cache (scope, account_id, payload_json, last_synced_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                entry.scope.value,
                entry.account_id,
                entry.payload_json,
                datetime_to_sql(entry.last_synced_at),
            ),
        )
        entry.id = cursor.lastrowid
        return entry

    def get(self, scope: LeaderboardScope, account_id: int) -> Optional[LeaderboardEntry]:
        row = self._connection.execute(
            "SELECT * FROM leaderboard_cache WHERE scope = ? AND account_id = ?",
            (scope.value, account_id),
        ).fetchone()
        return self._row_to_entry(row) if row else None

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> LeaderboardEntry:
        return LeaderboardEntry(
            id=row["id"],
            scope=LeaderboardScope(row["scope"]),
            account_id=row["account_id"],
            payload_json=row["payload_json"],
            last_synced_at=datetime_from_sql(row["last_synced_at"]),
        )
