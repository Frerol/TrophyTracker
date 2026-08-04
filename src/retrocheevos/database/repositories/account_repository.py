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

logger = logging.getLogger(__name__)


class AccountRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, account: Account) -> Account:
        """Insert a new account, or update it in place if the username already exists."""
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

    def update_last_synced(self, account_id: int, synced_at: datetime) -> None:
        self._connection.execute(
            "UPDATE accounts SET last_synced_at = ? WHERE id = ?",
            (datetime_to_sql(synced_at), account_id),
        )

    def remove(self, account_id: int) -> None:
        self._connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        logger.info("Removed account id=%d", account_id)

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            username=row["username"],
            api_key=row["api_key"],
            is_active=bool(row["is_active"]),
            last_synced_at=datetime_from_sql(row["last_synced_at"]),
        )
