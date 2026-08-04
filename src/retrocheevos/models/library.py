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
    id: Optional[int] = None


@dataclass
class WatchFolderMatch:
    """A file with a known destination console — either auto-detected with
    confidence, or picked by the user for a file that was ambiguous.

    `inner_member` is set when `file_path` is a single-file `.zip` and this
    match is for the file *inside* it (`console_detection._detect_single_file_zip`)
    — `apply_watch_folder_scan` extracts and hashes that member instead of
    the zip itself, then archives the original zip rather than deleting it.
    """

    file_path: str
    console_id: int
    inner_member: Optional[str] = None


@dataclass
class WatchFolderAmbiguity:
    """A file whose extension maps to more than one console and couldn't be
    narrowed down further — the user must pick one of `candidate_console_ids`.
    See `WatchFolderMatch.inner_member` for what this means for zips.
    """

    file_path: str
    candidate_console_ids: tuple[int, ...]
    inner_member: Optional[str] = None


@dataclass
class WatchFolderScanPreview:
    """Result of scanning a `RomFolder` without moving or recording anything
    yet (`library_service.preview_watch_folder_scan`). `unrecognized_paths`
    are files whose extension has no known console mapping at all.
    """

    rom_folder_id: int
    confident: list[WatchFolderMatch]
    ambiguous: list[WatchFolderAmbiguity]
    unrecognized_paths: list[str]
