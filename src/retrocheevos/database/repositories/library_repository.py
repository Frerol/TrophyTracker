"""Data access for `rom_folders` and `installed_roms` (Database.md 3.1, 3.2).

Every query is scoped to one account (`account_id`, schema v21). These two
tables were the last user-facing ones without an owner, which meant two
people sharing an install saw each other's ROM folders and library while
their lists, stats and preferences stayed properly separate.
"""

import sqlite3
from datetime import datetime
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.library import InstalledRom, RomFolder


class LibraryRepository:
    def __init__(
        self, connection: sqlite3.Connection, account_id: Optional[int] = None
    ) -> None:
        """`account_id` scopes every read and write.

        Optional rather than required because the app can legitimately have
        nobody signed in. The filter uses `IS` rather than `=` so a `None`
        account matches only rows that are themselves unowned — with `=`,
        SQL's NULL comparison would silently match *nothing*, including rows
        that legitimately have no owner after a migration on an
        account-less database.
        """
        self._connection = connection
        self._account_id = account_id

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Runs `sql` with the account filter appended. Centralised so a
        query added later can't quietly forget the scoping."""
        joiner = "AND" if " WHERE " in sql.upper() else "WHERE"
        return self._connection.execute(
            f"{sql} {joiner} account_id IS ?", (*params, self._account_id)
        ).fetchall()

    def _execute(self, sql: str, params: tuple = ()) -> None:
        joiner = "AND" if " WHERE " in sql.upper() else "WHERE"
        self._connection.execute(
            f"{sql} {joiner} account_id IS ?", (*params, self._account_id)
        )

    # --- rom_folders --------------------------------------------------

    def add_rom_folder(self, rom_folder: RomFolder) -> RomFolder:
        self._connection.execute(
            """
            INSERT INTO rom_folders (path, console_id, watch_enabled, account_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                console_id = excluded.console_id,
                watch_enabled = excluded.watch_enabled,
                account_id = excluded.account_id
            """,
            (
                rom_folder.path,
                rom_folder.console_id,
                rom_folder.watch_enabled,
                self._account_id,
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM rom_folders WHERE path = ?", (rom_folder.path,)
        ).fetchone()
        rom_folder.id = row["id"]
        return rom_folder

    def remove_rom_folder(self, rom_folder_id: int) -> None:
        self._execute("DELETE FROM rom_folders WHERE id = ?", (rom_folder_id,))

    def list_rom_folders(self) -> list[RomFolder]:
        rows = self._rows("SELECT * FROM rom_folders")
        return [
            self._row_to_rom_folder(row) for row in sorted(rows, key=lambda r: r["path"])
        ]

    def get_rom_folder(self, rom_folder_id: int) -> Optional[RomFolder]:
        rows = self._rows("SELECT * FROM rom_folders WHERE id = ?", (rom_folder_id,))
        return self._row_to_rom_folder(rows[0]) if rows else None

    # --- installed_roms -----------------------------------------------

    def add_installed_rom(self, installed_rom: InstalledRom) -> InstalledRom:
        """Idempotent: re-scanning the same file path updates the existing row."""
        self._connection.execute(
            """
            INSERT INTO installed_roms
                (game_id, file_path, hash, console_id, detected_at, account_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                game_id = excluded.game_id,
                hash = excluded.hash,
                console_id = excluded.console_id,
                detected_at = excluded.detected_at,
                account_id = excluded.account_id
            """,
            (
                installed_rom.game_id,
                installed_rom.file_path,
                installed_rom.hash,
                installed_rom.console_id,
                datetime_to_sql(installed_rom.detected_at),
                self._account_id,
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM installed_roms WHERE file_path = ?",
            (installed_rom.file_path,),
        ).fetchone()
        installed_rom.id = row["id"]
        return installed_rom

    def remove_installed_rom(self, installed_rom_id: int) -> None:
        self._execute("DELETE FROM installed_roms WHERE id = ?", (installed_rom_id,))

    def list_installed_roms(self, console_id: Optional[int] = None) -> list[InstalledRom]:
        if console_id is not None:
            rows = self._rows(
                "SELECT * FROM installed_roms WHERE console_id = ?", (console_id,)
            )
        else:
            rows = self._rows("SELECT * FROM installed_roms")
        return [self._row_to_installed_rom(row) for row in rows]

    def find_by_game_id(self, game_id: int) -> Optional[InstalledRom]:
        """First local match for a game. Multiple copies aren't disambiguated in the MVP."""
        rows = self._rows("SELECT * FROM installed_roms WHERE game_id = ?", (game_id,))
        return self._row_to_installed_rom(rows[0]) if rows else None

    def get_by_id(self, installed_rom_id: int) -> Optional[InstalledRom]:
        rows = self._rows("SELECT * FROM installed_roms WHERE id = ?", (installed_rom_id,))
        return self._row_to_installed_rom(rows[0]) if rows else None

    def set_game_id(self, installed_rom_id: int, game_id: int) -> None:
        """Manual match (UI.md 3.3) — hashing found no game for this ROM, or
        found the wrong one; the user picked the right one themselves.
        """
        self._execute(
            "UPDATE installed_roms SET game_id = ? WHERE id = ?",
            (game_id, installed_rom_id),
        )

    def set_last_played(self, installed_rom_id: int, played_at: datetime) -> None:
        """Stamped by `services/library_service.py::_launch_installed_rom` on
        every successful launch — deliberately not part of `add_installed_rom`'s
        upsert (see its own `ON CONFLICT` columns) so a re-scan of the same
        file never clobbers this back to NULL.
        """
        self._execute(
            "UPDATE installed_roms SET last_played_at = ? WHERE id = ?",
            (datetime_to_sql(played_at), installed_rom_id),
        )

    def get_last_played_by_game_id(self) -> dict[int, datetime]:
        """Most recent `last_played_at` per matched game, across every local
        copy of it — powers Continue Playing's recency ordering
        (`core/dashboard.py`).

        Reduced in Python rather than with `MAX(...) GROUP BY`, because the
        account filter has to be appended by `_rows` and a GROUP BY would put
        it in the wrong place. A handful of installed ROMs makes the
        difference immaterial.
        """
        rows = self._rows(
            "SELECT game_id, last_played_at FROM installed_roms "
            "WHERE game_id IS NOT NULL AND last_played_at IS NOT NULL"
        )
        latest: dict[int, datetime] = {}
        for row in rows:
            played_at = datetime_from_sql(row["last_played_at"])
            if played_at is None:
                continue
            current = latest.get(row["game_id"])
            if current is None or played_at > current:
                latest[row["game_id"]] = played_at
        return latest

    def get_unmatched_installed_roms(self) -> list[InstalledRom]:
        """ROMs no hash match (and no manual match yet) resolved to a game —
        Home's Continue Playing shows these as a fallback rather than
        hiding them entirely.
        """
        rows = self._rows("SELECT * FROM installed_roms WHERE game_id IS NULL")
        return [self._row_to_installed_rom(row) for row in rows]

    def get_installed_game_ids(self) -> set[int]:
        """Game IDs with at least one matched local ROM — drives the Installed status/icon."""
        rows = self._rows(
            "SELECT DISTINCT game_id FROM installed_roms WHERE game_id IS NOT NULL"
        )
        return {row["game_id"] for row in rows}

    def get_installed_file_paths(self) -> set[str]:
        """Every file path already recorded — lets folder scanning skip files
        that were already scanned/matched.
        """
        rows = self._rows("SELECT file_path FROM installed_roms")
        return {row["file_path"] for row in rows}

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
            last_played_at=datetime_from_sql(row["last_played_at"]),
        )
