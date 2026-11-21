"""Library DTOs — map to `rom_folders` and `installed_roms` (Database.md 3.1, 3.2)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from retrocheevos.models.game import Game


@dataclass
class RomFolder:
    path: str
    watch_enabled: bool
    console_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class InstalledRom:
    file_path: str
    hash: str  # Empty when the playable container has no compatible hasher.
    console_id: int
    game_id: Optional[int] = None
    detected_at: Optional[datetime] = None
    # When this ROM was last successfully launched through the app (any
    # entry point — Home, Library, Explorer all converge on the same
    # launch helper). None if never launched. Powers Continue Playing's
    # recency ordering (`core/dashboard.py`).
    last_played_at: Optional[datetime] = None
    # Fingerprint captured at hash time (R04). A rescan compares these
    # against the file on disk: same size and same high-resolution mtime
    # means the file is unchanged and can be skipped without re-reading it.
    # None on rows written before schema v26, which forces one rehash.
    file_size: Optional[int] = None
    file_mtime_ns: Optional[int] = None
    # True when `game_id` came from the user's "Match to Game…" rather than
    # from a hash hit. A changed file must never silently overwrite this.
    manual_match: bool = False
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
    failed_paths: list[str] = field(default_factory=list)
    failed_folders: list[str] = field(default_factory=list)
    # Files already recorded whose size/mtime no longer match the stored
    # fingerprint — re-hashed and re-matched during this scan (R04).
    changed_paths: list[str] = field(default_factory=list)
    # Changed files whose user-picked "Match to Game…" was kept rather than
    # overwritten by whatever the new hash resolved to.
    preserved_manual_matches: list[str] = field(default_factory=list)


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
    # ROMs whose `game_id` came from a manual match and was kept even though
    # the new hash resolved to a different game (or nothing). These are the
    # ones worth reviewing by hand — the file changed underneath a choice the
    # user made, so the app reports it instead of deciding for them.
    manual_matches_preserved: list[str] = field(default_factory=list)
    # Files whose hash moved during this pass — their in-flight artwork
    # loads must be invalidated (R04).
    changed_paths: list[str] = field(default_factory=list)


@dataclass
class LibraryEntry:
    """One card in the Library grid (R22): a matched game, or an installed ROM
    that matched no catalog game (`kind == "rom"`, D9's "Unmatched").

    Progress fields are None when nothing is known — never zero by default.
    `achievements_unlocked/total` are RetroAchievements' combined count (D8).
    """

    kind: str  # "game" or "rom"
    title: str
    console_id: int
    file_paths: list[str]
    game: Optional["Game"] = None
    rom: Optional[InstalledRom] = None
    last_played_at: Optional[datetime] = None
    achievements_unlocked: Optional[int] = None
    achievements_total: Optional[int] = None
    percent_complete: Optional[float] = None
    mastered: bool = False
    has_emulator: bool = False

    @property
    def key(self) -> tuple[str, int]:
        """Stable identity across refreshes: ("game", id) or ("rom", id)."""
        return (self.kind, self.game.id if self.game is not None else self.rom.id)
