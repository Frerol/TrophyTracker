"""Game icon caching for the Recent Activity feed — mirrors
`library/user_pics.py`'s shape (same confirmed base URL,
`https://i.retroachievements.org`), keyed by game id. Kept separate from
`library/game_images.py`'s own cache: that one is keyed to games synced
into the local library, and feed entries can reference games the account
has never synced (a followed friend's game).
"""

from pathlib import Path

from retrocheevos.library.game_images import build_image_url, download_image  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACTIVITY_ICON_CACHE_DIR = PROJECT_ROOT / "cache" / "activity_icons"


def cached_activity_icon_path(game_id: int) -> Path:
    """Where `game_id`'s icon lives locally, whether or not it's downloaded yet."""
    return ACTIVITY_ICON_CACHE_DIR / f"{game_id}.png"
