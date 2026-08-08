"""Data access for `user_list_definitions` and `user_lists` (Database.md 4.1,
schema v15).

Membership is addressed by `list_id` throughout. The older `list_type` column
is still written — it is `NOT NULL` and predates this — but nothing reads it
to decide anything any more: `get_list_types_for_game` used to do
`ListType(row["list_type"])`, which raised `ValueError` on any value outside
the enum and so would have crashed the moment a user created a list of their
own. It is gone; callers ask for `list_id`s and look the definitions up.

`abandoned`/`completed` exclusion from default Explorer results and other
list-membership rules are enforced by Core, not here (Database.md 4.1).
"""

import sqlite3
from datetime import datetime
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.list_definition import ListDefinition
from retrocheevos.models.list_entry import ListEntry
from retrocheevos.utils.enums import ListType

# Written into the legacy `user_lists.list_type` column for a game added to a
# list the user created. The column is NOT NULL so it needs *something*, and
# a shared sentinel is safer than the list's own name: names can collide with
# a `ListType` value ("blocked"), and any old code path still reading that
# column would then treat a custom list as the real Blocked list.
CUSTOM_LIST_TYPE_MARKER = "custom"


class ListRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    # --- definitions -------------------------------------------------

    def create_definition(self, definition: ListDefinition) -> ListDefinition:
        """Idempotent on `(account_id, name)` — re-running the predefined
        bootstrap must not raise or duplicate."""
        self._connection.execute(
            """
            INSERT INTO user_list_definitions (account_id, name, slug, is_predefined, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id, name) DO NOTHING
            """,
            (
                definition.account_id,
                definition.name,
                definition.slug.value if definition.slug else None,
                definition.is_predefined,
                datetime_to_sql(definition.created_at or datetime.now()),
            ),
        )
        row = self._connection.execute(
            "SELECT * FROM user_list_definitions WHERE account_id = ? AND name = ?",
            (definition.account_id, definition.name),
        ).fetchone()
        return self._row_to_definition(row)

    def rename_definition(self, list_id: int, name: str) -> None:
        self._connection.execute(
            "UPDATE user_list_definitions SET name = ? WHERE id = ?", (name, list_id)
        )

    def delete_definition(self, list_id: int) -> None:
        """Membership rows go first — `user_lists.list_id` references this
        table, so leaving them would either fail the foreign key or strand
        rows pointing at a list that no longer exists."""
        self._connection.execute("DELETE FROM user_lists WHERE list_id = ?", (list_id,))
        self._connection.execute("DELETE FROM user_list_definitions WHERE id = ?", (list_id,))

    def list_definitions(self, account_id: int) -> list[ListDefinition]:
        """Predefined first, then the user's own alphabetically — a stable
        order so the selector doesn't reshuffle as lists are created."""
        rows = self._connection.execute(
            "SELECT * FROM user_list_definitions WHERE account_id = ? "
            "ORDER BY is_predefined DESC, name COLLATE NOCASE",
            (account_id,),
        ).fetchall()
        return [self._row_to_definition(row) for row in rows]

    def get_definition(self, list_id: int) -> Optional[ListDefinition]:
        row = self._connection.execute(
            "SELECT * FROM user_list_definitions WHERE id = ?", (list_id,)
        ).fetchone()
        return self._row_to_definition(row) if row else None

    # --- membership --------------------------------------------------

    def add_to_list(self, entry: ListEntry) -> None:
        """No-op if the game is already in that list for this account.

        The `WHERE list_id IS NOT NULL` on the conflict target is required,
        not decorative: the index it refers to is a *partial* index, and
        SQLite raises "ON CONFLICT clause does not match any PRIMARY KEY or
        UNIQUE constraint" unless the target repeats the index's predicate.
        """
        self._connection.execute(
            """
            INSERT INTO user_lists (account_id, game_id, list_type, list_id, added_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id, game_id, list_id) WHERE list_id IS NOT NULL DO NOTHING
            """,
            (
                entry.account_id,
                entry.game_id,
                entry.list_type.value if entry.list_type else CUSTOM_LIST_TYPE_MARKER,
                entry.list_id,
                datetime_to_sql(entry.added_at),
            ),
        )

    def remove_from_list(self, account_id: int, game_id: int, list_id: int) -> None:
        self._connection.execute(
            "DELETE FROM user_lists WHERE account_id = ? AND game_id = ? AND list_id = ?",
            (account_id, game_id, list_id),
        )

    def get_list_ids_for_game(self, account_id: int, game_id: int) -> set[int]:
        rows = self._connection.execute(
            "SELECT list_id FROM user_lists "
            "WHERE account_id = ? AND game_id = ? AND list_id IS NOT NULL",
            (account_id, game_id),
        ).fetchall()
        return {row["list_id"] for row in rows}

    def get_game_ids_in_list(self, account_id: int, list_id: int) -> set[int]:
        rows = self._connection.execute(
            "SELECT game_id FROM user_lists WHERE account_id = ? AND list_id = ?",
            (account_id, list_id),
        ).fetchall()
        return {row["game_id"] for row in rows}

    def get_game_ids_by_slug(self, account_id: int, slug: ListType) -> set[int]:
        """Membership of a predefined list without having to resolve its id
        first — this is the hot path for Explorer's blocked-game filter, which
        runs on every search.
        """
        rows = self._connection.execute(
            "SELECT l.game_id FROM user_lists l "
            "JOIN user_list_definitions d ON d.id = l.list_id "
            "WHERE l.account_id = ? AND d.slug = ?",
            (account_id, slug.value),
        ).fetchall()
        return {row["game_id"] for row in rows}

    @staticmethod
    def _row_to_definition(row: sqlite3.Row) -> ListDefinition:
        raw_slug = row["slug"]
        return ListDefinition(
            id=row["id"],
            account_id=row["account_id"],
            name=row["name"],
            # Tolerant on purpose: a slug that isn't a known `ListType` (an
            # older list, or one from a future version) degrades to a plain
            # user list instead of raising, which is what the old
            # `ListType(...)` call did.
            slug=ListType(raw_slug) if raw_slug in _KNOWN_SLUGS else None,
            is_predefined=bool(row["is_predefined"]),
            created_at=datetime_from_sql(row["created_at"]),
        )


_KNOWN_SLUGS = {list_type.value for list_type in ListType}
