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


BADGE_IMAGE_CACHE_DIR = paths.cache_dir("badge_images")


def cached_badge_image_path(image_path: str) -> Path:
    """Where an award image (`/Images/012345.png`) lives locally; keyed by
    the file name, which RA uses as the image id."""
    return BADGE_IMAGE_CACHE_DIR / Path(image_path).name
