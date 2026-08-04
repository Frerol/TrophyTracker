"""Data access for the `rom_destinations` table (Database.md-adjacent — see
`schema.CREATE_TABLES_V5`)."""

import sqlite3
from typing import Optional

from retrocheevos.models.rom_destination import RomDestination


class RomDestinationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, destination: RomDestination) -> None:
        self._connection.execute(
            """
            INSERT INTO rom_destinations (console_id, path)
            VALUES (?, ?)
            ON CONFLICT(console_id) DO UPDATE SET path = excluded.path
            """,
            (destination.console_id, destination.path),
        )

    def get(self, console_id: int) -> Optional[RomDestination]:
        row = self._connection.execute(
            "SELECT * FROM rom_destinations WHERE console_id = ?", (console_id,)
        ).fetchone()
        return self._row_to_destination(row) if row else None

    def list_all(self) -> list[RomDestination]:
        rows = self._connection.execute(
            "SELECT * FROM rom_destinations ORDER BY console_id"
        ).fetchall()
        return [self._row_to_destination(row) for row in rows]

    def remove(self, console_id: int) -> None:
        self._connection.execute(
            "DELETE FROM rom_destinations WHERE console_id = ?", (console_id,)
        )

    @staticmethod
    def _row_to_destination(row: sqlite3.Row) -> RomDestination:
        return RomDestination(console_id=row["console_id"], path=row["path"])
