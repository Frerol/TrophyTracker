"""Data access for the `consoles` reference table (Database.md 2.2)."""

import sqlite3
from typing import Optional

from retrocheevos.models.console import Console


class ConsoleRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, console: Console) -> None:
        """Insert or update a console. Ids come from RetroAchievements, never autoincrement."""
        self._connection.execute(
            """
            INSERT INTO consoles (id, name, icon_path)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, icon_path = excluded.icon_path
            """,
            (console.id, console.name, console.icon_path),
        )

    def get_by_id(self, console_id: int) -> Optional[Console]:
        row = self._connection.execute(
            "SELECT * FROM consoles WHERE id = ?", (console_id,)
        ).fetchone()
        return self._row_to_console(row) if row else None

    def get_by_name(self, name: str) -> Optional[Console]:
        row = self._connection.execute(
            "SELECT * FROM consoles WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_console(row) if row else None

    def list_all(self) -> list[Console]:
        rows = self._connection.execute("SELECT * FROM consoles ORDER BY name").fetchall()
        return [self._row_to_console(row) for row in rows]

    @staticmethod
    def _row_to_console(row: sqlite3.Row) -> Console:
        return Console(id=row["id"], name=row["name"], icon_path=row["icon_path"])
