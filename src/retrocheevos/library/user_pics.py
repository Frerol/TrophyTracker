"""User profile picture caching — mirrors `library/game_images.py`'s shape
(same confirmed base URL, `https://i.retroachievements.org`), keyed by
username instead of game id.

It used to re-export that module's `build_image_url`/`download_image` for
convenience; nothing ever imported them from here (`services/image_service.py`
takes them from `game_images` directly), so the re-export is gone.
"""

from pathlib import Path

from retrocheevos import paths

USER_PIC_CACHE_DIR = paths.cache_dir("user_pics")


def cached_user_pic_path(username: str) -> Path:
    """Where `username`'s profile photo lives locally, whether or not it's downloaded yet."""
    return USER_PIC_CACHE_DIR / f"{username}.png"
