"""Data access for the `user_lists` table (Database.md 4.1).

`abandoned`/`completed` exclusion from default Explorer results and other
list-membership rules are enforced by Core, not here (Database.md 4.1).
"""

import sqlite3

from retrocheevos.database.serialization import datetime_to_sql
from retrocheevos.models.list_entry import ListEntry
from retrocheevos.utils.enums import ListType


class ListRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add_to_list(self, entry: ListEntry) -> None:
        """No-op if the game is already in that list for this account."""
        self._connection.execute(
            """
            INSERT INTO user_lists (account_id, game_id, list_type, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id, game_id, list_type) DO NOTHING
            """,
            (
                entry.account_id,
                entry.game_id,
                entry.list_type.value,
                datetime_to_sql(entry.added_at),
            ),
        )

    def remove_from_list(self, account_id: int, game_id: int, list_type: ListType) -> None:
        self._connection.execute(
            "DELETE FROM user_lists WHERE account_id = ? AND game_id = ? AND list_type = ?",
            (account_id, game_id, list_type.value),
        )

    def get_list_types_for_game(self, account_id: int, game_id: int) -> list[ListType]:
        rows = self._connection.execute(
            "SELECT list_type FROM user_lists WHERE account_id = ? AND game_id = ?",
            (account_id, game_id),
        ).fetchall()
        return [ListType(row["list_type"]) for row in rows]

    def get_game_ids_in_list(self, account_id: int, list_type: ListType) -> set[int]:
        rows = self._connection.execute(
            "SELECT game_id FROM user_lists WHERE account_id = ? AND list_type = ?",
            (account_id, list_type.value),
        ).fetchall()
        return {row["game_id"] for row in rows}
