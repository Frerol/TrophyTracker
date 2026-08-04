"""Data access for the `console_quick_links` table."""

import sqlite3
from typing import Optional

from retrocheevos.models.quick_link import QuickLink


class QuickLinkRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, quick_link: QuickLink) -> None:
        self._connection.execute(
            """
            INSERT INTO console_quick_links (console_id, url)
            VALUES (?, ?)
            ON CONFLICT(console_id) DO UPDATE SET url = excluded.url
            """,
            (quick_link.console_id, quick_link.url),
        )

    def get(self, console_id: int) -> Optional[QuickLink]:
        row = self._connection.execute(
            "SELECT * FROM console_quick_links WHERE console_id = ?", (console_id,)
        ).fetchone()
        return self._row_to_quick_link(row) if row else None

    def list_all(self) -> list[QuickLink]:
        rows = self._connection.execute(
            "SELECT * FROM console_quick_links ORDER BY console_id"
        ).fetchall()
        return [self._row_to_quick_link(row) for row in rows]

    def remove(self, console_id: int) -> None:
        self._connection.execute(
            "DELETE FROM console_quick_links WHERE console_id = ?", (console_id,)
        )

    @staticmethod
    def _row_to_quick_link(row: sqlite3.Row) -> QuickLink:
        return QuickLink(console_id=row["console_id"], url=row["url"])
