"""ROM folder management, manual ROM matching, Watch Folder scanning, and
emulator launching (UI.md 3.3).
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from retrocheevos.database.connection import create_connection, get_connection
from retrocheevos.database.repositories.emulator_config_repository import (
    EmulatorConfigRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.quick_link_repository import QuickLinkRepository
from retrocheevos.database.repositories.rom_destination_repository import (
    RomDestinationRepository,
)
from retrocheevos.library.console_detection import detect_console
from retrocheevos.library.hashing import compute_rom_hash
from retrocheevos.library.launcher import launch_emulator
from retrocheevos.library.organizer import move_rom, resolve_destination
from retrocheevos.library.zip_extraction import extract_member
from retrocheevos.models.emulator_config import EmulatorConfig
from retrocheevos.models.library import (
    InstalledRom,
    RomFolder,
    WatchFolderAmbiguity,
    WatchFolderMatch,
    WatchFolderScanPreview,
)
from retrocheevos.models.quick_link import QuickLink
from retrocheevos.models.rom_destination import RomDestination

# Where `apply_watch_folder_scan` archives an original zip after extracting
# its single ROM member — never deleted automatically (see `apply_watch_folder_scan`).
ALREADY_EXTRACTED_DIRNAME = "already-extracted"


class GameNotInstalledError(Exception):
    """No local ROM is matched to this game yet."""


class RomFileMissingError(Exception):
    """The matched ROM's file path no longer exists on disk."""


class EmulatorNotConfiguredError(Exception):
    """No emulator is configured for this game's console (see Settings)."""


class RomFolderNotFoundError(Exception):
    """No `rom_folders` row with this ID (it may have been removed since scanning)."""


class RomDestinationNotConfiguredError(Exception):
    """No destination folder is configured for this console (Settings > ROM Destinations)."""


def _normalize_path_for_comparison(path: str) -> str:
    """Watch Folder scanning discovers files via `Path.rglob`, which yields
    OS-native separators; `installed_roms.file_path` may hold whatever
    separator style the manual Scan file dialog produced. Comparing raw
    strings would let already-scanned files slip through as "new" and get
    reorganized again — normalize both sides before comparing.
    """
    return str(Path(path).resolve()).casefold()


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


def get_installed_game_ids() -> set[int]:
    """Game IDs with a matched local ROM — powers the Explorer table's
    "Installed" column (distinct from the `installed_only` *filter*, which
    `core/explorer.py` already applies internally).
    """
    with get_connection() as connection:
        return LibraryRepository(connection).get_installed_game_ids()


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
    rom_hash = compute_rom_hash(Path(file_path), console_id)
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


def set_rom_destination(console_id: int, path: str) -> RomDestination:
    with get_connection() as connection:
        destination = RomDestination(console_id=console_id, path=path)
        RomDestinationRepository(connection).upsert(destination)
        return destination


def remove_rom_destination(console_id: int) -> None:
    with get_connection() as connection:
        RomDestinationRepository(connection).remove(console_id)


def list_rom_destinations() -> list[RomDestination]:
    with get_connection() as connection:
        return RomDestinationRepository(connection).list_all()


def set_quick_link(console_id: int, url: str) -> QuickLink:
    with get_connection() as connection:
        quick_link = QuickLink(console_id=console_id, url=url)
        QuickLinkRepository(connection).upsert(quick_link)
        return quick_link


def remove_quick_link(console_id: int) -> None:
    with get_connection() as connection:
        QuickLinkRepository(connection).remove(console_id)


def list_quick_links() -> list[QuickLink]:
    with get_connection() as connection:
        return QuickLinkRepository(connection).list_all()


def get_quick_link(console_id: int) -> Optional[QuickLink]:
    with get_connection() as connection:
        return QuickLinkRepository(connection).get(console_id)


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


def preview_watch_folder_scan(rom_folder_id: int) -> WatchFolderScanPreview:
    """Read-only Watch Folder scan (UI.md 3.3 "Manual 'Scan now' action"):
    walks the folder, detects each not-yet-installed file's console, and
    reports what *would* happen — nothing is moved or recorded yet, so the
    GUI can show the user a plan before touching any files. Already-installed
    files are left untouched entirely (Database.md 7: `installed_roms` only
    refreshes on a scan event, not silently reorganized on every scan).

    Runs file I/O — call from a background thread, not the UI thread
    (CodingStandards' threading model).
    """
    with get_connection() as connection:
        rom_folder = LibraryRepository(connection).get_rom_folder(rom_folder_id)
        if rom_folder is None:
            raise RomFolderNotFoundError(f"ROM folder {rom_folder_id} not found")
        already_installed = {
            _normalize_path_for_comparison(path)
            for path in LibraryRepository(connection).get_installed_file_paths()
        }

    already_extracted_folder = Path(rom_folder.path) / ALREADY_EXTRACTED_DIRNAME
    confident: list[WatchFolderMatch] = []
    ambiguous: list[WatchFolderAmbiguity] = []
    unrecognized_paths: list[str] = []

    for file_path in Path(rom_folder.path).rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.is_relative_to(already_extracted_folder):
            continue  # archived originals — already handled, never re-processed
        if _normalize_path_for_comparison(str(file_path)) in already_installed:
            continue

        result = detect_console(file_path)
        if result.is_confident:
            confident.append(
                WatchFolderMatch(
                    file_path=str(file_path),
                    console_id=result.console_id,
                    inner_member=result.inner_member,
                )
            )
        elif result.candidate_console_ids:
            ambiguous.append(
                WatchFolderAmbiguity(
                    file_path=str(file_path),
                    candidate_console_ids=result.candidate_console_ids,
                    inner_member=result.inner_member,
                )
            )
        else:
            unrecognized_paths.append(str(file_path))

    return WatchFolderScanPreview(
        rom_folder_id=rom_folder_id,
        confident=confident,
        ambiguous=ambiguous,
        unrecognized_paths=unrecognized_paths,
    )


def apply_watch_folder_scan(
    rom_folder_id: int, decisions: list[WatchFolderMatch]
) -> list[InstalledRom]:
    """Moves each decided file into its console's configured destination
    folder (Settings > ROM Destinations) and records it (UI.md 3.3).
    `decisions` combines the preview's auto-detected matches with the user's
    manual picks for its ambiguous ones — nothing here guesses a console on
    its own, and nothing moves without a destination already configured for
    that console (`RomDestinationNotConfiguredError` otherwise — the review
    dialog is expected to only offer consoles that already have one, so
    hitting this means something changed between preview and apply).

    For a decision with `inner_member` set (a single-file zip), the member is
    extracted and *that* file is moved/hashed/recorded — never the zip
    itself. Only once that has fully succeeded is the original zip moved to
    `<rom folder>/already-extracted/` (never deleted automatically: kept
    around to build confidence in extraction before enabling that). If
    extraction or recording fails partway, the original zip is left
    untouched in place so a retry starts clean rather than from an
    already-archived-but-unrecorded state.

    `rom_folder_id` only confirms the watched folder still exists; unlike the
    previous design, it no longer determines where files end up — the
    destination is per-console, not nested under the watched folder.

    Runs file I/O — call from a background thread, not the UI thread
    (CodingStandards' threading model).
    """
    with get_connection() as connection:
        rom_folder = LibraryRepository(connection).get_rom_folder(rom_folder_id)
        if rom_folder is None:
            raise RomFolderNotFoundError(f"ROM folder {rom_folder_id} not found")
        destinations = {
            destination.console_id: destination.path
            for destination in RomDestinationRepository(connection).list_all()
        }

    already_extracted_folder = Path(rom_folder.path) / ALREADY_EXTRACTED_DIRNAME
    results: list[InstalledRom] = []
    for decision in decisions:
        destination_path = destinations.get(decision.console_id)
        if destination_path is None:
            raise RomDestinationNotConfiguredError(
                f"No ROM destination configured for console {decision.console_id}. "
                "Set one in Settings > ROM Destinations."
            )

        source_path = Path(decision.file_path)

        if decision.inner_member:
            with tempfile.TemporaryDirectory() as scratch_dir:
                extracted_path = extract_member(source_path, decision.inner_member, Path(scratch_dir))
                destination = resolve_destination(Path(destination_path), extracted_path)
                moved_path = move_rom(extracted_path, destination)
                results.append(scan_and_record_rom(str(moved_path), decision.console_id))

            archive_destination = resolve_destination(already_extracted_folder, source_path)
            move_rom(source_path, archive_destination)
        else:
            destination = resolve_destination(Path(destination_path), source_path)
            moved_path = move_rom(source_path, destination)
            results.append(scan_and_record_rom(str(moved_path), decision.console_id))

    return results
