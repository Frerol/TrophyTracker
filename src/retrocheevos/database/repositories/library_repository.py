"""Data access for `rom_folders` and `installed_roms` (Database.md 3.1, 3.2)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.library import InstalledRom, RomFolder


class LibraryRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add_rom_folder(self, rom_folder: RomFolder) -> RomFolder:
        self._connection.execute(
            """
            INSERT INTO rom_folders (path, console_id, watch_enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                console_id = excluded.console_id,
                watch_enabled = excluded.watch_enabled
            """,
            (rom_folder.path, rom_folder.console_id, rom_folder.watch_enabled),
        )
        row = self._connection.execute(
            "SELECT id FROM rom_folders WHERE path = ?", (rom_folder.path,)
        ).fetchone()
        rom_folder.id = row["id"]
        return rom_folder

    def remove_rom_folder(self, rom_folder_id: int) -> None:
        self._connection.execute("DELETE FROM rom_folders WHERE id = ?", (rom_folder_id,))

    def list_rom_folders(self) -> list[RomFolder]:
        rows = self._connection.execute("SELECT * FROM rom_folders ORDER BY path").fetchall()
        return [self._row_to_rom_folder(row) for row in rows]

    def set_watch_enabled(self, rom_folder_id: int, enabled: bool) -> None:
        self._connection.execute(
            "UPDATE rom_folders SET watch_enabled = ? WHERE id = ?",
            (enabled, rom_folder_id),
        )

    def add_installed_rom(self, installed_rom: InstalledRom) -> InstalledRom:
        """Idempotent: re-scanning the same file path updates the existing row."""
        self._connection.execute(
            """
            INSERT INTO installed_roms (game_id, file_path, hash, console_id, detected_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                game_id = excluded.game_id,
                hash = excluded.hash,
                console_id = excluded.console_id,
                detected_at = excluded.detected_at
            """,
            (
                installed_rom.game_id,
                installed_rom.file_path,
                installed_rom.hash,
                installed_rom.console_id,
                datetime_to_sql(installed_rom.detected_at),
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM installed_roms WHERE file_path = ?", (installed_rom.file_path,)
        ).fetchone()
        installed_rom.id = row["id"]
        return installed_rom

    def remove_installed_rom(self, installed_rom_id: int) -> None:
        self._connection.execute("DELETE FROM installed_roms WHERE id = ?", (installed_rom_id,))

    def list_installed_roms(self, console_id: Optional[int] = None) -> list[InstalledRom]:
        if console_id is not None:
            rows = self._connection.execute(
                "SELECT * FROM installed_roms WHERE console_id = ?", (console_id,)
            ).fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM installed_roms").fetchall()
        return [self._row_to_installed_rom(row) for row in rows]

    def find_by_game_id(self, game_id: int) -> Optional[InstalledRom]:
        """First local match for a game. Multiple copies aren't disambiguated in the MVP."""
        row = self._connection.execute(
            "SELECT * FROM installed_roms WHERE game_id = ? LIMIT 1", (game_id,)
        ).fetchone()
        return self._row_to_installed_rom(row) if row else None

    def get_installed_game_ids(self) -> set[int]:
        """Game IDs with at least one matched local ROM — drives the Installed status/icon."""
        rows = self._connection.execute(
            "SELECT DISTINCT game_id FROM installed_roms WHERE game_id IS NOT NULL"
        ).fetchall()
        return {row["game_id"] for row in rows}

    @staticmethod
    def _row_to_rom_folder(row: sqlite3.Row) -> RomFolder:
        return RomFolder(
            id=row["id"],
            path=row["path"],
            console_id=row["console_id"],
            watch_enabled=bool(row["watch_enabled"]),
        )

    @staticmethod
    def _row_to_installed_rom(row: sqlite3.Row) -> InstalledRom:
        return InstalledRom(
            id=row["id"],
            game_id=row["game_id"],
            file_path=row["file_path"],
            hash=row["hash"],
            console_id=row["console_id"],
            detected_at=datetime_from_sql(row["detected_at"]),
        )
