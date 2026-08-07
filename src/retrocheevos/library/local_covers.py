"""Local cover-art caching for `installed_roms` with no matched game
(Architecture.md — Library layer), mirroring `library/game_images.py`'s
shape minus the download — the source here is a file the user picked on
their own machine, not a URL.

Keyed by `installed_roms.id`, not `games.id`: an unmatched ROM has no game
row to key by (`core/dashboard.py`'s Continue Playing fallback). If the ROM
later gets matched (manually or by hash), it starts using the real game's
RA cover instead — this cache simply stops being read for it, never deleted.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCAL_COVER_CACHE_DIR = PROJECT_ROOT / "cache" / "local_covers"


def cached_local_cover_path(installed_rom_id: int) -> Path:
    """Where a user-picked cover for this ROM lives locally, whether or not
    one has been set yet — check `.exists()` before treating it as set.
    """
    return LOCAL_COVER_CACHE_DIR / f"{installed_rom_id}.png"
