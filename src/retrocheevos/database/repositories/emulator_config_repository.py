"""Data access for the `emulator_configs` table (Database.md 3.4)."""

import sqlite3
from typing import Optional

from retrocheevos.models.emulator_config import EmulatorConfig


class EmulatorConfigRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, config: EmulatorConfig) -> None:
        self._connection.execute(
            """
            INSERT INTO emulator_configs
                (console_id, executable_path, arguments_template, core_path)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(console_id) DO UPDATE SET
                executable_path = excluded.executable_path,
                arguments_template = excluded.arguments_template,
                core_path = excluded.core_path
            """,
            (
                config.console_id,
                config.executable_path,
                config.arguments_template,
                config.core_path,
            ),
        )

    def get(self, console_id: int) -> Optional[EmulatorConfig]:
        row = self._connection.execute(
            "SELECT * FROM emulator_configs WHERE console_id = ?", (console_id,)
        ).fetchone()
        return self._row_to_config(row) if row else None

    def list_all(self) -> list[EmulatorConfig]:
        rows = self._connection.execute(
            "SELECT * FROM emulator_configs ORDER BY console_id"
        ).fetchall()
        return [self._row_to_config(row) for row in rows]

    def remove(self, console_id: int) -> None:
        self._connection.execute(
            "DELETE FROM emulator_configs WHERE console_id = ?", (console_id,)
        )

    @staticmethod
    def _row_to_config(row: sqlite3.Row) -> EmulatorConfig:
        return EmulatorConfig(
            console_id=row["console_id"],
            executable_path=row["executable_path"],
            arguments_template=row["arguments_template"],
            core_path=row["core_path"],
        )
