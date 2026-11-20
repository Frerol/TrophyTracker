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

        Store the fallback in the caller's transaction. Vault reconciliation
        runs only after the entire account operation has committed.
        """
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
                account.api_key,
                account.is_active,
                datetime_to_sql(account.last_synced_at),
            ),
        )
        # Cancel an old deletion intent if this username is being re-added.
        self._connection.execute(
            "DELETE FROM pending_credential_deletions WHERE username = ?",
            (account.username,),
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
        if self._connection.execute(
            "SELECT 1 FROM accounts WHERE id = ?", (account_id,)
        ).fetchone() is None:
            raise ValueError("The selected account no longer exists")
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
        # Read before the row goes: the vault is keyed by username.
        row = self._connection.execute(
            "SELECT username FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()

        for table in self._ACCOUNT_CHILD_TABLES:
            self._connection.execute(
                f"DELETE FROM {table} WHERE account_id = ?", (account_id,)
            )
        self._connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

        # The deletion intent and account removal commit together. A crash or
        # unavailable vault cannot lose the retry, nor delete a rolled-back key.
        if row is not None:
            self._connection.execute(
                "INSERT OR REPLACE INTO pending_credential_deletions "
                "(username, created_at) VALUES (?, ?)",
                (row["username"], datetime.now().isoformat()),
            )
        logger.info("Removed account id=%d and its data", account_id)

    @staticmethod
    def cleanup_pending_credentials(connection=None):
        from retrocheevos.services.session_service import cleanup_pending_credentials
        if connection is None:
            return cleanup_pending_credentials()
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        return AccountRepository._cleanup_pending(connection, credential_store)

    @staticmethod
    def _cleanup_pending(connection, store):
        """Caller must hold a write transaction to serialize account changes."""
        cleaned = 0
        rows = connection.execute("SELECT username FROM pending_credential_deletions").fetchall()
        for row in rows:
            username = row["username"]
            # Never delete a credential now owned by a re-created account.
            exists = connection.execute(
                "SELECT 1 FROM accounts WHERE username = ?", (username,)
            ).fetchone()
            try:
                if exists is None and store.delete_key(username) is False:
                    continue
            except Exception:
                logger.warning("Deferred credential cleanup failed for %s", username)
                continue
            connection.execute(
                "DELETE FROM pending_credential_deletions WHERE username = ?", (username,)
            )
            cleaned += 1
        return cleaned

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
