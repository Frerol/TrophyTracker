"""ROM folder management, manual ROM matching, ROM Location scanning, and
emulator launching (UI.md 3.3).

The scanning here **reads only** — it detects what is already installed in
folders the user organized themselves. It does not move, rename, extract in
place, or delete anything. The previous design (Watch Folder + ROM
Destinations) organized files for the user; that was removed in Bloco 11
along with `library/organizer.py`, so nothing in this module writes to disk
any more.
"""

import logging
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from retrocheevos.database.connection import create_connection, get_connection
from retrocheevos.core.console_reference import CONSOLE_NAMES
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.database.repositories.emulator_config_repository import (
    EmulatorConfigRepository,
)
from retrocheevos.core.lists import get_installed_games as _get_installed_games
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.library.console_detection import detect_console
from retrocheevos.library.hashing import compute_rom_hash
from retrocheevos.library.rom_traversal import iter_rom_files
from retrocheevos.library.launcher import launch_emulator
from retrocheevos.library.rom_title import (
    COVER_MATCH_CUTOFF,
    derive_title_from_filename,
    find_best_title_match,
)
from retrocheevos.library.zip_extraction import extract_member
from retrocheevos.models.emulator_config import EmulatorConfig
from retrocheevos.models.console import Console
from retrocheevos.models.game import Game
from retrocheevos.models.library import (
    InstalledRom,
    LibraryEntry,
    RehashResult,
    RomFolder,
    RomFolderScanResult,
)
from retrocheevos.services import session_service, play_session_service
from retrocheevos.utils.cancellation import OperationCancelled, raise_if_cancelled


logger = logging.getLogger(__name__)


def _active_account_id() -> Optional[int]:
    account = session_service.get_active_account()
    return account.id if account is not None else None


def _library_repo(connection) -> LibraryRepository:
    """Repository bound to whoever is signed in (schema v21).

    Every call site goes through here rather than constructing the
    repository directly, so scoping can't be forgotten in one place and
    leak another account's ROMs.
    """
    return LibraryRepository(connection, _active_account_id())

# Skipped before console detection even runs. These sit in ROM folders and
# some of them *do* map to a console extension (`.bin` is the worst
# offender — a save, a BIOS and a disc track all share it), so detection
# alone happily recorded them and they piled up in "Unmatched ROMs" where
# there is nothing the user can do about them.
NON_ROM_EXTENSIONS = frozenset(
    {
        # Saves and emulator state
        "sav", "srm", "st0", "st1", "st2", "st3", "st4", "st5", "st6", "st7",
        "st8", "st9", "state", "ss0", "ss1", "mcr", "mcd", "vmp", "vms", "gci",
        "dsv", "sa1", "rtc", "brk", "cht", "sram", "eep", "fla",
        # Patches and metadata
        "ips", "bps", "ups", "xdelta", "dat", "xml", "nfo", "sfv", "md5",
        "sha1", "txt", "log", "ini", "cfg", "json", "db", "url",
        # Art and documents
        "png", "jpg", "jpeg", "gif", "bmp", "webp", "pdf", "html", "htm",
        # Archives that aren't the single-ROM zips `console_detection` peeks
        # into, plus general junk
        "rar", "7z", "tar", "gz", "exe", "dll", "lnk", "bat", "ini",
    }
)
# Whole directories that never hold ROMs, matched case-insensitively on any
# path segment.
SKIPPED_DIR_NAMES = frozenset(
    {"saves", "savestates", "states", "screenshots", "media", "images",
     "covers", "artwork", "cheats", "patches", "system", "bios",
     "already-extracted", "__macosx"}
)


class GameNotInstalledError(Exception):
    """No local ROM is matched to this game yet."""


class RomFileMissingError(Exception):
    """The matched ROM's file path no longer exists on disk."""


class EmulatorNotConfiguredError(Exception):
    """No emulator is configured for this game's console (see Settings)."""


class RomFolderNotFoundError(Exception):
    """No `rom_folders` row with this ID (it may have been removed since scanning)."""


class InstalledRomNotFoundError(Exception):
    """No `installed_roms` row with this ID (it may have been removed since scanning)."""


def _normalize_path_for_comparison(path: str) -> str:
    """Folder scanning discovers files via streaming traversal, which yields
    OS-native separators; `installed_roms.file_path` may hold whatever
    separator style the manual Scan file dialog produced. Comparing raw
    strings would let already-scanned files slip through as "new" and get
    re-hashed on every scan — normalize both sides before comparing.
    """
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def _file_fingerprint(path: Path) -> tuple[Optional[int], Optional[int]]:
    """Size and nanosecond mtime — R04's cheap "did this file change?" test.

    `st_mtime_ns` rather than `st_mtime`: filesystem mtimes are often stored
    at sub-second resolution, and two edits within the same second are
    exactly the kind of change a whole-second comparison misses. Returns
    `(None, None)` when the file can't be stat'ed; a NULL fingerprint forces
    a rehash rather than being mistaken for "unchanged".
    """
    try:
        stat_result = path.stat()
    except OSError:
        return None, None
    return stat_result.st_size, stat_result.st_mtime_ns


def add_rom_folder(
    path: str, console_id: Optional[int] = None, watch_enabled: bool = False
) -> RomFolder:
    with get_connection() as connection:
        _ensure_config_console(connection, console_id)
        return _library_repo(connection).add_rom_folder(
            RomFolder(path=str(Path(path).expanduser().resolve()), console_id=console_id, watch_enabled=watch_enabled)
        )


def remove_rom_folder(rom_folder_id: int) -> None:
    with get_connection() as connection:
        _library_repo(connection).remove_rom_folder(rom_folder_id)


def list_rom_folders() -> list[RomFolder]:
    with get_connection() as connection:
        return _library_repo(connection).list_rom_folders()


def list_installed_roms(console_id: Optional[int] = None) -> list[InstalledRom]:
    with get_connection() as connection:
        return _library_repo(connection).list_installed_roms(console_id)


def get_installed_games() -> list[Game]:
    """Full `Game` rows for the Library page's grid — blocked games excluded
    (`core/lists.py::get_installed_games`)."""
    account = session_service.get_active_account()
    if account is None:
        return []
    with get_connection() as connection:
        return _get_installed_games(
            account.id,
            list_repository=ListRepository(connection),
            game_repository=GameRepository(connection),
            library_repository=_library_repo(connection),
        )


def list_library_entries() -> list[LibraryEntry]:
    """Every card of the Library grid for the displayed account (R22):
    installed games (blocked ones excluded, as before) followed by unmatched
    ROMs, each with progress, mastery and emulator availability. Ordered by
    title so the grid is stable across refreshes."""
    account = session_service.get_active_account()
    if account is None:
        return []
    from retrocheevos.database.repositories.game_completion_repository import (
        GameCompletionRepository,
    )
    from retrocheevos.library.rom_title import derive_title_from_filename

    with get_connection() as connection:
        library = _library_repo(connection)
        games = _get_installed_games(
            account.id,
            list_repository=ListRepository(connection),
            game_repository=GameRepository(connection),
            library_repository=library,
        )
        roms = library.list_installed_roms()
        completion = GameCompletionRepository(connection)
        percents = completion.get_all_for_account(account.id)
        counts = completion.get_achievement_counts_for_account(account.id)
        mastered = completion.get_mastered_game_ids(account.id)
        emulators = {config.console_id for config in EmulatorConfigRepository(connection).list_all()}

    paths_by_game: dict[int, list[str]] = {}
    roms_by_game: dict[int, list[InstalledRom]] = {}
    last_played: dict[int, datetime] = {}
    for rom in roms:
        if rom.game_id is None:
            continue
        paths_by_game.setdefault(rom.game_id, []).append(rom.file_path)
        roms_by_game.setdefault(rom.game_id, []).append(rom)
        if rom.last_played_at is not None and (
            rom.game_id not in last_played or rom.last_played_at > last_played[rom.game_id]
        ):
            last_played[rom.game_id] = rom.last_played_at

    entries = []
    for game in games:
        unlocked, total = counts.get(game.id, (None, None))
        entries.append(LibraryEntry(
            kind="game", title=game.title, console_id=game.console_id,
            file_paths=paths_by_game.get(game.id, []), game=game,
            roms=roms_by_game.get(game.id, []),
            last_played_at=last_played.get(game.id),
            achievements_unlocked=unlocked, achievements_total=total,
            percent_complete=percents.get(game.id),
            mastered=game.id in mastered,
            has_emulator=game.console_id in emulators,
        ))
    entries.sort(key=lambda entry: entry.title.casefold())
    unmatched = [
        LibraryEntry(
            kind="rom", title=derive_title_from_filename(rom.file_path),
            console_id=rom.console_id, file_paths=[rom.file_path], rom=rom, roms=[rom],
            last_played_at=rom.last_played_at,
            has_emulator=rom.console_id in emulators,
        )
        for rom in roms if rom.game_id is None
    ]
    unmatched.sort(key=lambda entry: entry.title.casefold())
    return entries + unmatched


def get_installed_game_ids() -> set[int]:
    """Game IDs with a matched local ROM — powers the Explorer table's
    "Installed" column (distinct from the `installed_only` *filter*, which
    `core/explorer.py` already applies internally).
    """
    with get_connection() as connection:
        return _library_repo(connection).get_installed_game_ids()


def remove_installed_rom(installed_rom_id: int) -> None:
    """Forget a recorded ROM. Removes the `installed_roms` row only — the
    file on disk is never touched, in keeping with the rest of this module
    (nothing here writes to disk since Bloco 11).

    A later scan of the same folder will pick the file up again; the filters
    in `_is_not_a_rom` are what stop junk coming back, this is the manual
    escape hatch for whatever slips through them.
    """
    with get_connection() as connection:
        _library_repo(connection).remove_installed_rom(installed_rom_id)


def remove_installed_roms_for_game(game_id: int) -> int:
    """Forget every local copy of one game — what "remove from Library" means
    for a matched card, since the grid is keyed by game and a game can have
    more than one ROM recorded against it. Files on disk are untouched.
    """
    removed = 0
    with get_connection() as connection:
        repository = _library_repo(connection)
        for installed_rom in repository.list_installed_roms():
            if installed_rom.game_id == game_id:
                repository.remove_installed_rom(installed_rom.id)
                removed += 1
    return removed


def get_installed_rom(installed_rom_id: int) -> Optional[InstalledRom]:
    with get_connection() as connection:
        return _library_repo(connection).get_by_id(installed_rom_id)


def match_installed_rom_to_game(installed_rom_id: int, game_id: int) -> None:
    """Manual match (UI.md 3.3): the user picked which game a ROM that
    hashing couldn't resolve actually is. Also usable to correct a wrong
    match — no check that the ROM was previously unmatched.

    Marked `manual_match` so a later hash-driven rematch (a rescan, a forced
    rehash, or the hash backfill's `rematch_unmatched_roms`) reports a
    disagreement instead of overwriting the user's choice.
    """
    with get_connection() as connection:
        _library_repo(connection).set_game_id(installed_rom_id, game_id, manual=True)


def use_automatic_match(installed_rom_id: int, *, rehash: bool = True) -> Optional[int]:
    """Undo a manual match: the ROM goes back to whatever its hash matches in
    the local catalog, or to unmatched if nothing does.

    The file is hashed again first (`rehash=True`): a stored hash can predate
    the current hasher — before RAHasher, or an RVZ before dolphin-tool — and
    matching that would undo the user's choice for nothing. Hashing can take
    a few seconds (a disc through dolphin-tool), so call it off the GUI
    thread. If the file is gone or cannot be hashed, the stored hash is used.
    Returns the game id the ROM ends up with (None when it is unmatched).
    """
    with get_connection() as connection:
        rom = _library_repo(connection).get_by_id(installed_rom_id)
    if rom is None:
        return None
    rom_hash = rom.hash
    fingerprint = None
    path = Path(rom.file_path)
    if rehash and path.exists():
        try:
            fingerprint = _file_fingerprint(path)
            rom_hash = _hash_recorded_rom(path, rom.console_id)
        except Exception:  # noqa: BLE001 — fall back to the stored hash
            logger.exception("Could not re-hash %s; using its stored hash", rom.file_path)
            rom_hash, fingerprint = rom.hash, None
    with get_connection() as connection:
        repository = _library_repo(connection)
        if fingerprint is not None:
            repository.set_fingerprint(rom.id, *fingerprint)
        if rom_hash != rom.hash:
            logger.info("Re-hashed %s: %s -> %s", rom.file_path, rom.hash, rom_hash)
            repository.set_hash(rom.id, rom_hash)
        game_id = GameRepository(connection).find_game_id_by_hash(rom_hash) if rom_hash else None
        repository.set_game_id(rom.id, game_id, manual=False)
    logger.info("Automatic match for %s: game %s", rom.file_path, game_id)
    return game_id


def use_automatic_matches(installed_rom_ids: list[int]) -> list[Optional[int]]:
    """`use_automatic_match` for several copies (one card), in order."""
    return [use_automatic_match(rom_id) for rom_id in installed_rom_ids]


def consoles_needing_hashes() -> list[int]:
    """Consoles of unmatched, hashed ROMs whose catalog hashes were never
    fetched — automatic matching cannot work for them yet (R22)."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT r.console_id FROM installed_roms r
            WHERE r.account_id IS ? AND r.game_id IS NULL AND r.hash != ''
              AND NOT EXISTS (
                SELECT 1 FROM game_hashes h JOIN games g ON g.id = h.game_id
                WHERE g.console_id = r.console_id
              )
            ORDER BY r.console_id
            """,
            (_active_account_id(),),
        ).fetchall()
    return [row["console_id"] for row in rows]


def rematch_unmatched_roms() -> int:
    """Re-run hash matching over ROMs that are already recorded but unmatched.

    Matching happens once, at scan time (`record_installed_rom`), against
    whatever was in `game_hashes` then. That table was empty until the hash
    backfill existed, so every ROM scanned before it ran was recorded with
    `game_id = NULL` and would have stayed that way forever — a folder
    rescan skips files already in `installed_roms`, by design, because
    hashing is the expensive part.

    Costs nothing: the hash is already stored on each row, so this is a
    local lookup per ROM and no API calls at all. It is what turns the hours
    of hash syncing into actually-matched games.

    Returns how many ROMs got matched.
    """
    matched = 0
    with get_connection() as connection:
        repository = _library_repo(connection)
        game_repository = GameRepository(connection)
        for rom in repository.list_installed_roms():
            if rom.game_id is not None or not rom.hash:
                continue
            game_id = game_repository.find_game_id_by_hash(rom.hash)
            if game_id is not None:
                repository.set_game_id(rom.id, game_id)
                matched += 1

    logger.info("Re-matched %d previously unmatched ROM(s)", matched)
    return matched


def rehash_installed_roms(
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RehashResult:
    """Recompute every recorded ROM's hash with the current hasher, then
    re-match anything whose hash changed.

    This is also R04's **forced verification pass**: unlike a folder scan,
    it ignores the size/mtime fingerprint and re-reads every file, so a
    change the fingerprint couldn't see (same size, mtime restored) is still
    caught. It refreshes each row's fingerprint as it goes.

    `rematch_unmatched_roms` re-runs *matching* against the stored hash. This
    re-runs the *hashing*, which is the half that was unreachable: a folder
    rescan skips files already in `installed_roms` (deliberately — hashing is
    the expensive part), so a ROM recorded in 2025 kept its 2025 hash no
    matter how much the hashing improved afterwards. Three of them were
    provably wrong when this was written: two NES files whose iNES header the
    old whole-file MD5 never stripped, and a Dreamcast `.gdi` where it hashed
    the text index instead of the disc.

    Only writes when the hash actually changes, so a second run is a no-op
    against the database and every `last_played_at` survives.

    A **manual** match is never overwritten. If the new hash disagrees with
    the game the user picked, the row keeps the user's choice and the path is
    reported in `manual_matches_preserved` for review. An automatic match
    whose hash moved is re-resolved from the new hash — including clearing it
    when nothing matches, since the old match was a statement about the old
    bytes.

    `progress_callback(done, total, current_path)` runs on this thread.

    Runs file I/O and can shell out to RAHasher per ROM — call from a
    background thread (CodingStandards' threading model).
    """
    account_id = _active_account_id()
    with get_connection() as connection:
        roms = LibraryRepository(connection, account_id).list_installed_roms()

    total = len(roms)
    changed = 0
    newly_matched = 0
    missing: list[str] = []
    failed: list[str] = []
    manual_matches_preserved: list[str] = []
    changed_paths: list[str] = []

    for index, rom in enumerate(roms, start=1):
        raise_if_cancelled(should_cancel)
        if progress_callback is not None:
            progress_callback(index, total, rom.file_path)

        path = Path(rom.file_path)
        if not path.exists():
            missing.append(rom.file_path)
            continue

        file_size, file_mtime_ns = _file_fingerprint(path)
        try:
            new_hash = _hash_recorded_rom(path, rom.console_id)
        except Exception:  # noqa: BLE001 — one unreadable ROM mustn't end the pass
            logger.exception("Could not re-hash %s", rom.file_path)
            failed.append(rom.file_path)
            continue

        hash_changed = new_hash != rom.hash
        # A row with no game yet still deserves a matching attempt even when
        # its hash is unchanged — the hash table may have filled in since.
        needs_match = hash_changed or rom.game_id is None

        with get_connection() as connection:
            repository = LibraryRepository(connection, account_id)
            repository.set_fingerprint(rom.id, file_size, file_mtime_ns)
            if hash_changed:
                logger.info(
                    "Re-hashed %s: %s -> %s", rom.file_path, rom.hash, new_hash
                )
                repository.set_hash(rom.id, new_hash)
                changed += 1
                changed_paths.append(rom.file_path)

            if not needs_match:
                continue

            game_id = GameRepository(connection).find_game_id_by_hash(new_hash)
            if rom.manual_match:
                if rom.game_id is not None and game_id != rom.game_id:
                    manual_matches_preserved.append(rom.file_path)
                continue

            if game_id != rom.game_id:
                repository.set_game_id(rom.id, game_id)
                if game_id is not None:
                    newly_matched += 1

    logger.info(
        "Re-hash pass: %d checked, %d hashes changed, %d newly matched, "
        "%d missing, %d failed, %d manual match(es) preserved",
        total,
        changed,
        newly_matched,
        len(missing),
        len(failed),
        len(manual_matches_preserved),
    )
    return RehashResult(
        checked=total,
        changed=changed,
        newly_matched=newly_matched,
        missing=missing,
        failed=failed,
        manual_matches_preserved=manual_matches_preserved,
        changed_paths=changed_paths,
    )


def list_games_for_matching(console_id: int) -> list[Game]:
    """Every locally-synced game with achievements for one console, for the
    "Match to Game..." picker. Deliberately bypasses `core/explorer.py`'s
    account-scoped mastered/beaten/list exclusions — this is "which game is
    this file", not the Explorer's discovery view, so already-mastered or
    already-beaten games must still be pickable.
    """
    with get_connection() as connection:
        return GameRepository(connection).search(console_ids=[console_id])


def record_installed_rom(file_path: str, console_id: int, rom_hash: str) -> InstalledRom:
    """Match an already-computed hash to a known game (Database.md 2.4 — never
    assume compatibility without a hit). Use `scan_and_record_rom` for a real
    file — this exists separately for callers that already have the hash.
    """
    return _record_installed_rom_for_account(
        file_path, console_id, rom_hash, _active_account_id()
    )


def _record_installed_rom_for_account(
    file_path: str, console_id: int, rom_hash: str, account_id: Optional[int]
) -> InstalledRom:
    file_size, file_mtime_ns = _file_fingerprint(Path(file_path))
    with get_connection() as connection:
        game_id = GameRepository(connection).find_game_id_by_hash(rom_hash) if rom_hash else None
        return LibraryRepository(connection, account_id).add_installed_rom(
            InstalledRom(
                file_path=file_path,
                hash=rom_hash,
                console_id=console_id,
                game_id=game_id,
                detected_at=datetime.now(),
                file_size=file_size,
                file_mtime_ns=file_mtime_ns,
            )
        )


def scan_and_record_rom(file_path: str, console_id: int) -> InstalledRom:
    """Manual ROM matching (UI.md 3.3): hash one file the user pointed to and record/match it.

    Runs file I/O — call from a background thread, not the UI thread
    (CodingStandards' threading model).
    """
    account_id = _active_account_id()
    rom_hash = _hash_recorded_rom(Path(file_path), console_id)
    return _record_installed_rom_for_account(file_path, console_id, rom_hash, account_id)


def _ensure_config_console(connection: sqlite3.Connection, console_id: Optional[int]) -> None:
    """Persist offline reference data only when a local configuration needs it."""
    if console_id in CONSOLE_NAMES:
        ConsoleRepository(connection).add_if_missing(
            Console(id=console_id, name=CONSOLE_NAMES[console_id])
        )


def set_emulator_config(
    console_id: int,
    executable_path: str,
    arguments_template: Optional[str] = None,
    core_path: Optional[str] = None,
    flatpak_app_id: Optional[str] = None,
    flatpak_installation: Optional[str] = None,
) -> EmulatorConfig:
    with get_connection() as connection:
        _ensure_config_console(connection, console_id)
        config = EmulatorConfig(
            console_id=console_id,
            executable_path=executable_path,
            arguments_template=arguments_template or None,
            core_path=core_path or None,
            flatpak_app_id=flatpak_app_id or None,
            flatpak_installation=flatpak_installation if flatpak_app_id else None,
        )
        EmulatorConfigRepository(connection).upsert(config)
        return config


def remove_emulator_config(console_id: int) -> None:
    with get_connection() as connection:
        EmulatorConfigRepository(connection).remove(console_id)


def list_emulator_configs() -> list[EmulatorConfig]:
    with get_connection() as connection:
        return EmulatorConfigRepository(connection).list_all()


def _launch_installed_rom(
    installed_rom: InstalledRom, connection: sqlite3.Connection, account_id: Optional[int]
) -> subprocess.Popen:
    """Shared by `launch_game`/`launch_installed_rom` once each has already
    resolved its `InstalledRom` — validates the file still exists and an
    emulator is configured, then launches. Raises `RomFileMissingError` or
    `EmulatorNotConfiguredError`; caller's connection is still open here and
    closed by the caller, not this helper.

    Also stamps `last_played_at` (Continue Playing's recency ordering,
    `core/dashboard.py`) after process creation succeeds. This write uses
    the otherwise read-only connection (see `launch_game`'s docstring), so it's committed
    explicitly here rather than relying on `get_connection`'s auto-commit.
    """
    rom_path = Path(installed_rom.file_path)
    if not rom_path.exists():
        raise RomFileMissingError(f"ROM file no longer exists: {installed_rom.file_path}")

    emulator_config = EmulatorConfigRepository(connection).get(installed_rom.console_id)
    if emulator_config is None:
        raise EmulatorNotConfiguredError(
            f"No emulator configured for console {installed_rom.console_id}. "
            "Set one in Settings > Emulators."
        )

    game = (
        GameRepository(connection).get_by_id(installed_rom.game_id)
        if installed_rom.game_id is not None else None
    )
    process = launch_emulator(
        Path(emulator_config.executable_path),
        rom_path,
        emulator_config.arguments_template,
        core_path=Path(emulator_config.core_path) if emulator_config.core_path else None,
        flatpak_app_id=emulator_config.flatpak_app_id,
        flatpak_installation=emulator_config.flatpak_installation,
    )
    play_session_service.record_launch(
        account_id, installed_rom.game_id,
        game.title if game is not None else derive_title_from_filename(installed_rom.file_path),
        process,
    )

    # Record recency only after the emulator process exists. A persistence
    # failure here must not imply that the already-running emulator failed to
    # start or invite a duplicate launch.
    try:
        LibraryRepository(connection, account_id).set_last_played(installed_rom.id, datetime.now())
        connection.commit()
    except Exception as error:  # noqa: BLE001
        try:
            connection.rollback()
        except Exception:
            logger.warning("Emulator started; recency rollback also failed")
        logger.warning(
            "Emulator started but failed to record last_played_at for installed ROM %s: %s",
            installed_rom.id, error,
        )
    return process


def launch_game(game_id: int) -> subprocess.Popen:
    """Launch `game_id`'s matched local ROM in its console's configured emulator.

    Runs the emulator as an independent process (`library.launcher`) — call
    from a background thread, not the UI thread (CodingStandards' threading
    model). Raises `GameNotInstalledError`, `RomFileMissingError`, or
    `EmulatorNotConfiguredError` for the GUI to surface to the user.

    Uses `create_connection` directly rather than `get_connection`: this is
    read-only (no writes to commit/roll back), and the error cases above are
    expected control flow, not database failures — `get_connection` would
    log them as "Database operation failed, rolled back", which isn't true
    and would be misleading in `logs/`.
    """
    account_id = _active_account_id()
    connection = create_connection()
    try:
        installed_rom = LibraryRepository(connection, account_id).find_by_game_id(game_id)
        if installed_rom is None:
            raise GameNotInstalledError(f"Game {game_id} has no local ROM matched to it.")
        return _launch_installed_rom(installed_rom, connection, account_id)
    finally:
        connection.close()


def launch_installed_rom(installed_rom_id: int) -> subprocess.Popen:
    """Same as `launch_game`, but for a ROM Home's Continue Playing shows via
    `get_unmatched_installed_roms` — no `game_id` to look up by, so this
    starts from the `installed_roms` row's own id instead. Raises
    `InstalledRomNotFoundError`, `RomFileMissingError`, or
    `EmulatorNotConfiguredError`.
    """
    account_id = _active_account_id()
    connection = create_connection()
    try:
        installed_rom = LibraryRepository(connection, account_id).get_by_id(installed_rom_id)
        if installed_rom is None:
            raise InstalledRomNotFoundError(f"Installed ROM {installed_rom_id} not found.")
        return _launch_installed_rom(installed_rom, connection, account_id)
    finally:
        connection.close()


def scan_rom_folder(
    rom_folder_id: int,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RomFolderScanResult:
    """Walk a ROM folder and record what's installed, **without moving anything**.

    This is the whole point of the ROM Location page: the user has already
    organized their ROMs and just wants the app to know what's there. Every
    file stays exactly where it is.

    Files already in `installed_roms` are skipped outright — hashing is the
    expensive part of this loop, and re-hashing a folder that hasn't changed
    would make a rescan cost as much as the first scan. Only files whose
    console is *confidently* detected get recorded; ambiguous and
    unrecognized ones come back in the result for the page to show. Guessing
    a console would silently mis-hash the file and match it to the wrong
    game, which is harder to notice and undo than a file simply not being
    picked up.

    The folder's own `console_id` is passed to detection as a tie-breaker
    (see `console_detection._resolve`), which is what makes a folder of disc
    images scan to anything at all — `.chd`/`.cue`/`.bin`/`.iso` each map to
    several consoles, so before this a correctly configured PS1 or PS2 folder
    came back entirely "ambiguous".

    `progress_callback(discovered_entries, current_path)` reports directories
    and files as they are discovered, before detection or hashing. The total
    is unknown until traversal finishes. It runs on this thread, so it must not touch
    widgets directly (`gui/workers.py` marshals it).

    Runs file I/O — call from a background thread, not the UI thread
    (CodingStandards' threading model). Raises `RomFolderNotFoundError` if
    the folder row is gone.
    """
    return _scan_rom_folder_for_account(
        rom_folder_id,
        _active_account_id(),
        progress_callback,
        should_cancel=should_cancel,
    )


def _scan_rom_folder_for_account(
    rom_folder_id: int,
    account_id: Optional[int],
    progress_callback: Optional[Callable[[int, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RomFolderScanResult:
    with get_connection() as connection:
        repository = LibraryRepository(connection, account_id)
        rom_folder = repository.get_rom_folder(rom_folder_id)
        if rom_folder is None:
            raise RomFolderNotFoundError(f"ROM folder {rom_folder_id} not found")
        already_installed = {
            _normalize_path_for_comparison(rom.file_path): rom
            for rom in repository.list_installed_roms()
        }

    recorded: list[InstalledRom] = []
    ambiguous_paths: list[str] = []
    unrecognized_paths: list[str] = []
    failed_paths: list[str] = []
    changed_paths: list[str] = []
    preserved_manual_matches: list[str] = []
    already_known_count = 0

    folder_path = Path(rom_folder.path).expanduser().resolve()
    if not folder_path.is_dir():
        raise FileNotFoundError(f"ROM folder is not accessible: {folder_path}")
    def traversal_failed(path: Path, error: OSError) -> None:
        logger.warning("Could not traverse %s: %s", path, error)
        failed_paths.append(str(path))

    for file_path in iter_rom_files(
        folder_path, SKIPPED_DIR_NAMES, progress_callback, should_cancel,
        on_error=traversal_failed,
    ):
        raise_if_cancelled(should_cancel)
        if _is_not_a_rom(file_path.relative_to(folder_path)):
            continue

        existing = already_installed.get(_normalize_path_for_comparison(str(file_path)))
        if existing is not None:
            file_size, file_mtime_ns = _file_fingerprint(file_path)
            unchanged = (
                existing.file_size is not None
                and existing.file_mtime_ns is not None
                and existing.file_size == file_size
                and existing.file_mtime_ns == file_mtime_ns
            )
            if unchanged:
                already_known_count += 1
                continue

            # A recorded path whose file changed (or predates v26 and has no
            # fingerprint yet). Rehash it — this is the R04 gap a plain rescan
            # left open: the path was known, so it was skipped forever even
            # though the bytes underneath it were different.
            try:
                new_hash = _hash_recorded_rom(file_path, existing.console_id)
            except (OSError, ValueError):
                logger.exception("Could not re-scan changed ROM %s", file_path)
                failed_paths.append(str(file_path))
                continue

            changed_paths.append(str(file_path))
            with get_connection() as connection:
                repository = LibraryRepository(connection, account_id)
                repository.set_hash(existing.id, new_hash)
                repository.set_fingerprint(existing.id, file_size, file_mtime_ns)
                if existing.manual_match:
                    if existing.game_id is not None:
                        preserved_manual_matches.append(str(file_path))
                    continue
                game_id = (
                    GameRepository(connection).find_game_id_by_hash(new_hash)
                    if new_hash
                    else None
                )
                if game_id != existing.game_id:
                    repository.set_game_id(existing.id, game_id)
            continue

        detection = detect_console(file_path, rom_folder.console_id)
        if not detection.is_confident:
            if detection.candidate_console_ids:
                ambiguous_paths.append(str(file_path))
            else:
                unrecognized_paths.append(str(file_path))
            continue

        try:
            rom_hash = _hash_in_place(file_path, detection.console_id, detection.inner_member)
        except (OSError, ValueError):
            logger.exception("Could not scan ROM %s", file_path)
            failed_paths.append(str(file_path))
            continue
        recorded.append(
            _record_installed_rom_for_account(
                str(file_path), detection.console_id, rom_hash, account_id
            )
        )

    return RomFolderScanResult(
        rom_folder_id=rom_folder_id,
        recorded=recorded,
        already_known_count=already_known_count,
        ambiguous_paths=ambiguous_paths,
        unrecognized_paths=unrecognized_paths,
        failed_paths=failed_paths,
        changed_paths=changed_paths,
        preserved_manual_matches=preserved_manual_matches,
    )


def purge_non_rom_entries() -> int:
    """Delete `installed_roms` rows for files that are not ROMs, returning how
    many went.

    `_is_not_a_rom` only stops *new* scans recording junk — everything
    recorded before that filter existed is still in the table, which is why
    saves and box art kept showing up under "Unmatched ROMs" after the filter
    landed. This clears them out.

    Only ever removes rows whose path fails the same structural test a fresh
    scan would apply, and never touches the files themselves. A matched ROM
    is left alone regardless: if hashing tied it to a real game, the
    extension heuristic is the thing more likely to be wrong.
    """
    removed = 0
    with get_connection() as connection:
        repository = _library_repo(connection)
        roots = sorted(
            (Path(folder.path).expanduser().resolve() for folder in repository.list_rom_folders()),
            key=lambda root: len(root.parts), reverse=True,
        )
        for installed_rom in repository.list_installed_roms():
            if installed_rom.game_id is not None:
                continue
            path = Path(installed_rom.file_path).expanduser().resolve()
            root = next((root for root in roots if path.is_relative_to(root)), None)
            relative_path = path.relative_to(root) if root is not None else Path(path.name)
            if _is_not_a_rom(relative_path):
                repository.remove_installed_rom(installed_rom.id)
                removed += 1
    if removed:
        logger.info("Purged %d non-ROM entries from installed_roms", removed)
    return removed


def guess_games_for_unmatched_roms() -> dict[int, Game]:
    """Best-guess catalog game per unmatched ROM, keyed by `installed_roms.id`.

    Purely for **cover art**: an unmatched ROM has no `game_id`, so it had no
    picture at all, while the game it obviously is sits in the local catalog
    with artwork already synced. Matching on the title derived from the
    filename plus the ROM's console is enough to borrow that image.

    Nothing is written and no match is recorded — a guess good enough to show
    a picture is not good enough to claim the ROM *is* that game, which is
    what "Match to Game…" is for and what the achievement hashes decide. If
    the guess is wrong the user sees a wrong cover, not a wrong game.

    One catalog query per console present, not per ROM: a folder of 500 PSP
    ROMs would otherwise be 500 identical searches.
    """
    guesses: dict[int, Game] = {}
    with get_connection() as connection:
        game_repository = GameRepository(connection)
        unmatched = [
            rom
            for rom in _library_repo(connection).list_installed_roms()
            if rom.game_id is None
        ]
        by_console: dict[int, list[Game]] = {}
        for rom in unmatched:
            if rom.console_id not in by_console:
                by_console[rom.console_id] = game_repository.search(
                    console_ids=[rom.console_id]
                )
            candidates = by_console[rom.console_id]
            if not candidates:
                continue
            titles = {game.title: game for game in candidates}
            match = find_best_title_match(
                derive_title_from_filename(rom.file_path),
                list(titles),
                cutoff=COVER_MATCH_CUTOFF,
            )
            if match is not None:
                guesses[rom.id] = titles[match]
    return guesses


def purge_missing_roms() -> int:
    """Forget ROMs whose file is no longer on disk, returning how many went.

    Nothing was watching for this: `installed_roms` is only ever written by a
    scan, so deleting a file left its row behind and the game kept showing in
    the Library forever.

    **Guarded on the containing ROM folder still being reachable.** An
    unplugged external drive or a disconnected network share makes every path
    under it "missing", and without this check one launch with the drive off
    would wipe that whole console's library — indistinguishable, from the
    row's point of view, from the user deleting the files. If the folder
    can't be seen, its ROMs are left alone; if the folder is there and the
    file isn't, the file really is gone.

    Rows outside every configured folder (added via "Scan ROM File…") are
    checked directly, since there is no folder to vouch for them.
    """
    reachable_folders = [
        Path(folder.path) for folder in list_rom_folders() if Path(folder.path).is_dir()
    ]
    all_folders = [Path(folder.path) for folder in list_rom_folders()]

    removed = 0
    with get_connection() as connection:
        repository = _library_repo(connection)
        for installed_rom in repository.list_installed_roms():
            path = Path(installed_rom.file_path)
            if path.exists():
                continue
            parent_folder = next(
                (folder for folder in all_folders if path.is_relative_to(folder)), None
            )
            if parent_folder is not None and parent_folder not in reachable_folders:
                continue  # drive/share is offline — not the user deleting things
            repository.remove_installed_rom(installed_rom.id)
            removed += 1
    if removed:
        logger.info("Purged %d installed ROMs whose files are gone", removed)
    return removed


def _is_not_a_rom(file_path: Path) -> bool:
    """Cheap structural rejection, before any hashing or console detection.

    Not reported as "unrecognized" either — these aren't files the user needs
    told about, they're the ordinary contents of a ROM folder. Only things
    that *might* be a ROM and couldn't be placed are worth surfacing.
    """
    if file_path.name.startswith("."):
        return True
    if file_path.suffix.lstrip(".").casefold() in NON_ROM_EXTENSIONS:
        return True
    return any(part.casefold() in SKIPPED_DIR_NAMES for part in file_path.parts)


def scan_all_rom_folders(
    progress_callback: Optional[Callable[[int, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RomFolderScanResult:
    """Scan every configured ROM folder and return one combined result.

    Sequential, not parallel: the expensive part is hashing, which is disk
    bound — running folders concurrently would have them competing for the
    same drive rather than going faster. A folder that fails is logged and
    skipped so one bad path doesn't abandon the rest.

    `rom_folder_id` on the result is `-1`: the aggregate doesn't belong to
    any single folder, and inventing one of theirs would be a lie the caller
    might act on.

    Runs file I/O — call from a background thread (CodingStandards).
    """
    combined = RomFolderScanResult(
        rom_folder_id=-1,
        recorded=[],
        already_known_count=0,
        ambiguous_paths=[],
        unrecognized_paths=[],
    )
    account_id = _active_account_id()
    with get_connection() as connection:
        folders = LibraryRepository(connection, account_id).list_rom_folders()
    for rom_folder in folders:
        raise_if_cancelled(should_cancel)
        try:
            result = _scan_rom_folder_for_account(
                rom_folder.id,
                account_id,
                progress_callback,
                should_cancel=should_cancel,
            )
        except OperationCancelled:
            raise
        except Exception:
            logger.exception("Scan failed for ROM folder %s", rom_folder.path)
            combined.failed_folders.append(rom_folder.path)
            continue
        combined.recorded.extend(result.recorded)
        combined.already_known_count += result.already_known_count
        combined.ambiguous_paths.extend(result.ambiguous_paths)
        combined.unrecognized_paths.extend(result.unrecognized_paths)
        combined.failed_paths.extend(result.failed_paths)
        combined.changed_paths.extend(result.changed_paths)
        combined.preserved_manual_matches.extend(result.preserved_manual_matches)
    return combined


def _hash_recorded_rom(file_path: Path, console_id: int) -> str:
    """Use the same single-ROM ZIP handling for manual scans and rehashes."""
    inner_member = (
        detect_console(file_path, console_id).inner_member
        if file_path.suffix.lower() == ".zip" else None
    )
    return _hash_in_place(file_path, console_id, inner_member)


def _hash_in_place(
    file_path: Path, console_id: int, inner_member: Optional[str]
) -> str:
    """Hash for a file that is staying put.

    A single-file zip is the awkward case: RA hashes the ROM *inside* the
    archive, so hashing the zip's own bytes would never match anything. The
    member is extracted to a scratch directory, hashed there, and the scratch
    copy is discarded — the recorded `file_path` is still the zip, which is
    what the user has on disk and what the emulator gets handed. The old
    Watch Folder code solved this by permanently extracting and moving the
    file; this does not, by design.
    """
    if inner_member is None:
        return compute_rom_hash(file_path, console_id)

    with tempfile.TemporaryDirectory() as scratch_dir:
        extracted_path = extract_member(file_path, inner_member, Path(scratch_dir))
        return compute_rom_hash(extracted_path, console_id)
