"""Data access for the `accounts` table (Database.md 2.1).

Callers own the transaction boundary — no method here commits; use
`connection.get_connection()` (or commit explicitly) around a unit of work.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.account import Account
# Lives under `services/` by filename, but it is a data store like this one —
# it imports nothing from the rest of the app, so there is no cycle here.
from retrocheevos.services import credential_store

logger = logging.getLogger(__name__)


class AccountRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, account: Account) -> Account:
        """Insert a new account, or update it in place if the username already exists.

        The API key goes to the OS credential vault, and the database column
        is written **empty** — but only once the vault has confirmed the
        write. If it hasn't, the column keeps the key, because a key stored
        nowhere is an account that can never authenticate again.
        """
        stored_in_vault = credential_store.set_key(account.username, account.api_key)
        self._connection.execute(
            """
            INSERT INTO accounts (username, api_key, is_active, last_synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                api_key = excluded.api_key,
                is_active = excluded.is_active,
                last_synced_at = excluded.last_synced_at
            """,
            (
                account.username,
                "" if stored_in_vault else account.api_key,
                account.is_active,
                datetime_to_sql(account.last_synced_at),
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM accounts WHERE username = ?", (account.username,)
        ).fetchone()
        account.id = row["id"]
        logger.info("Added/updated account '%s' (id=%d)", account.username, account.id)
        return account

    def get_by_id(self, account_id: int) -> Optional[Account]:
        row = self._connection.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return self._row_to_account(row) if row else None

    def get_active(self) -> Optional[Account]:
        row = self._connection.execute("SELECT * FROM accounts WHERE is_active = 1").fetchone()
        return self._row_to_account(row) if row else None

    def list_all(self) -> list[Account]:
        rows = self._connection.execute("SELECT * FROM accounts ORDER BY username").fetchall()
        return [self._row_to_account(row) for row in rows]

    def set_active(self, account_id: int) -> None:
        """Mark `account_id` as active and deactivate every other account."""
        self._connection.execute("UPDATE accounts SET is_active = 0")
        self._connection.execute("UPDATE accounts SET is_active = 1 WHERE id = ?", (account_id,))
        logger.info("Switched active account to id=%d", account_id)

    def deactivate_all(self) -> None:
        """Logout: no account stays active. Accounts themselves are untouched
        (still listed in Settings) — distinct from `remove`, which deletes one."""
        self._connection.execute("UPDATE accounts SET is_active = 0")
        logger.info("Deactivated all accounts (logout)")

    def update_last_synced(self, account_id: int, synced_at: datetime) -> None:
        self._connection.execute(
            "UPDATE accounts SET last_synced_at = ? WHERE id = ?",
            (datetime_to_sql(synced_at), account_id),
        )

    # Every table with a foreign key to `accounts`, in an order that respects
    # the one dependency among them: `user_lists.list_id` points at
    # `user_list_definitions.id`, so the memberships go before the lists.
    #
    # Derived from `PRAGMA foreign_key_list` over the whole schema rather than
    # written from memory — `rom_folders` and `installed_roms` only joined
    # this set in migration v21, and missing one is invisible until a delete
    # fails on it.
    _ACCOUNT_CHILD_TABLES = (
        "user_lists",
        "user_list_definitions",
        "user_achievements",
        "game_completion",
        "badges",
        "profile_stats",
        "notifications",
        "user_preferences",
        "installed_roms",
        "rom_folders",
    )

    def remove(self, account_id: int) -> None:
        """Delete an account **and everything belonging to it**.

        Every one of those foreign keys is `ON DELETE NO ACTION`, so deleting
        the account row on its own left ten kinds of orphan behind and SQLite
        refused with `FOREIGN KEY constraint failed` — the crash this
        replaces. Changing them to `ON DELETE CASCADE` would mean rebuilding
        ten tables (SQLite cannot alter a foreign key in place), so the
        deletion is explicit here instead.

        `WHERE account_id = ?` deliberately leaves rows whose `account_id` is
        NULL: those belong to nobody, and removing one person's account is
        not the moment to guess who they were meant for.
        """
        # Read before the row goes: the vault is keyed by username, and
        # removing the account without removing its credential would leave
        # the key behind in Credential Manager after the user asked for
        # everything to be deleted.
        row = self._connection.execute(
            "SELECT username FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()

        for table in self._ACCOUNT_CHILD_TABLES:
            self._connection.execute(
                f"DELETE FROM {table} WHERE account_id = ?", (account_id,)
            )
        self._connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

        if row is not None:
            credential_store.delete_key(row["username"])
        logger.info("Removed account id=%d and its data", account_id)

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Account:
        """A nonempty column is a pending vault write and takes precedence.

        Hydrating here rather than in a service is deliberate — this is the
        single funnel every `Account` passes through, so no caller can end up
        holding one with an empty key and discover it only when a request
        401s.
        """
        username = row["username"]
        api_key = row["api_key"] or credential_store.get_key(username) or ""
        return Account(
            id=row["id"],
            username=username,
            api_key=api_key,
            is_active=bool(row["is_active"]),
            last_synced_at=datetime_from_sql(row["last_synced_at"]),
        )
