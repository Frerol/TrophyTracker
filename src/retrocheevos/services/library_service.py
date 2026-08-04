"""ROM folder management, manual ROM matching, and emulator launching
(UI.md 3.3; MVP: no auto-scan yet).
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from retrocheevos.database.connection import create_connection, get_connection
from retrocheevos.database.repositories.emulator_config_repository import (
    EmulatorConfigRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.library.hashing import compute_rom_hash
from retrocheevos.library.launcher import launch_emulator
from retrocheevos.models.emulator_config import EmulatorConfig
from retrocheevos.models.library import InstalledRom, RomFolder


class GameNotInstalledError(Exception):
    """No local ROM is matched to this game yet."""


class RomFileMissingError(Exception):
    """The matched ROM's file path no longer exists on disk."""


class EmulatorNotConfiguredError(Exception):
    """No emulator is configured for this game's console (see Settings)."""


def add_rom_folder(
    path: str, console_id: Optional[int] = None, watch_enabled: bool = False
) -> RomFolder:
    with get_connection() as connection:
        return LibraryRepository(connection).add_rom_folder(
            RomFolder(path=path, console_id=console_id, watch_enabled=watch_enabled)
        )


def remove_rom_folder(rom_folder_id: int) -> None:
    with get_connection() as connection:
        LibraryRepository(connection).remove_rom_folder(rom_folder_id)


def list_rom_folders() -> list[RomFolder]:
    with get_connection() as connection:
        return LibraryRepository(connection).list_rom_folders()


def list_installed_roms(console_id: Optional[int] = None) -> list[InstalledRom]:
    with get_connection() as connection:
        return LibraryRepository(connection).list_installed_roms(console_id)


def record_installed_rom(file_path: str, console_id: int, rom_hash: str) -> InstalledRom:
    """Match an already-computed hash to a known game (Database.md 2.4 — never
    assume compatibility without a hit). Use `scan_and_record_rom` for a real
    file — this exists separately for callers that already have the hash.
    """
    with get_connection() as connection:
        game_id = GameRepository(connection).find_game_id_by_hash(rom_hash)
        return LibraryRepository(connection).add_installed_rom(
            InstalledRom(
                file_path=file_path,
                hash=rom_hash,
                console_id=console_id,
                game_id=game_id,
                detected_at=datetime.now(),
            )
        )


def scan_and_record_rom(file_path: str, console_id: int) -> InstalledRom:
    """Manual ROM matching (UI.md 3.3): hash one file the user pointed to and record/match it.

    Runs file I/O — call from a background thread, not the UI thread
    (CodingStandards' threading model).
    """
    rom_hash = compute_rom_hash(Path(file_path))
    return record_installed_rom(file_path, console_id, rom_hash)


def set_emulator_config(
    console_id: int, executable_path: str, arguments_template: Optional[str] = None
) -> EmulatorConfig:
    with get_connection() as connection:
        config = EmulatorConfig(
            console_id=console_id,
            executable_path=executable_path,
            arguments_template=arguments_template or None,
        )
        EmulatorConfigRepository(connection).upsert(config)
        return config


def remove_emulator_config(console_id: int) -> None:
    with get_connection() as connection:
        EmulatorConfigRepository(connection).remove(console_id)


def list_emulator_configs() -> list[EmulatorConfig]:
    with get_connection() as connection:
        return EmulatorConfigRepository(connection).list_all()


def launch_game(game_id: int) -> subprocess.Popen:
    """Launch `game_id`'s matched local ROM in its console's configured emulator.

    Runs the emulator as an independent process (`library.launcher`) — call
    from a background thread, not the UI thread (CodingStandards' threading
    model). Raises `GameNotInstalledError`, `RomFileMissingError`, or
    `EmulatorNotConfiguredError` for the GUI to surface to the user.

    Uses `create_connection` directly rather than `get_connection`: this is
    read-only (no writes to commit/roll back), and the three error cases
    above are expected control flow, not database failures — `get_connection`
    would log them as "Database operation failed, rolled back", which isn't
    true and would be misleading in `logs/`.
    """
    connection = create_connection()
    try:
        installed_rom = LibraryRepository(connection).find_by_game_id(game_id)
        if installed_rom is None:
            raise GameNotInstalledError(f"Game {game_id} has no local ROM matched to it.")

        rom_path = Path(installed_rom.file_path)
        if not rom_path.exists():
            raise RomFileMissingError(f"ROM file no longer exists: {installed_rom.file_path}")

        emulator_config = EmulatorConfigRepository(connection).get(installed_rom.console_id)
        if emulator_config is None:
            raise EmulatorNotConfiguredError(
                f"No emulator configured for console {installed_rom.console_id}. "
                "Set one in Settings > Emulators."
            )
    finally:
        connection.close()

    return launch_emulator(
        Path(emulator_config.executable_path), rom_path, emulator_config.arguments_template
    )
