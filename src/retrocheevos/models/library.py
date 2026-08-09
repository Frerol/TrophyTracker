"""Library DTOs — map to `rom_folders` and `installed_roms` (Database.md 3.1, 3.2)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RomFolder:
    path: str
    watch_enabled: bool
    console_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class InstalledRom:
    file_path: str
    hash: str
    console_id: int
    game_id: Optional[int] = None
    detected_at: Optional[datetime] = None
    # When this ROM was last successfully launched through the app (any
    # entry point — Home, Library, Explorer all converge on the same
    # launch helper). None if never launched. Powers Continue Playing's
    # recency ordering (`core/dashboard.py`).
    last_played_at: Optional[datetime] = None
    id: Optional[int] = None


@dataclass
class RomFolderScanResult:
    """What `library_service.scan_rom_folder` found and recorded.

    The scan never moves, renames, or deletes anything — the ROM Location
    page points at folders the user has already organized themselves, so the
    only job is working out what is in them. Files that can't be pinned to a
    single console are reported rather than guessed at: filing a ROM under
    the wrong console is worse than leaving it out.
    """

    rom_folder_id: int
    recorded: list["InstalledRom"]
    already_known_count: int
    # Extension maps to more than one console and nothing narrowed it down.
    ambiguous_paths: list[str]
    # Extension maps to no known console at all — saves, patches, box art,
    # readme files, and everything else that lives alongside real ROMs.
    unrecognized_paths: list[str]


@dataclass
class RehashResult:
    """What `library_service.rehash_installed_roms` did.

    `changed` is the number that matters: it is how many ROMs were carrying a
    hash from an older, worse hasher. Zero means the library was already up
    to date, which is the normal outcome on a second run.
    """

    checked: int
    changed: int
    newly_matched: int
    # Files that have since been deleted or moved — left in the table
    # untouched, since a missing file is `purge_missing_installed_roms`'
    # business, not this function's.
    missing: list[str]
    # Hashing raised or the hasher refused the file. Reported rather than
    # swallowed: a format that silently fails to re-hash is exactly the kind
    # of thing that stays broken because nobody hears about it.
    failed: list[str]
