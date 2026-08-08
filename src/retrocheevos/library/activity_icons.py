"""Game icon caching for the Recent Activity feed — mirrors
`library/user_pics.py`'s shape (same confirmed base URL,
`https://i.retroachievements.org`), keyed by game id. Kept separate from
`library/game_images.py`'s own cache: that one is keyed to games synced
into the local library, and feed entries can reference games the account
has never synced (a followed friend's game).
"""

from pathlib import Path

from retrocheevos import paths

ACTIVITY_ICON_CACHE_DIR = paths.cache_dir("activity_icons")


def cached_activity_icon_path(game_id: int) -> Path:
    """Where `game_id`'s icon lives locally, whether or not it's downloaded yet."""
    return ACTIVITY_ICON_CACHE_DIR / f"{game_id}.png"
