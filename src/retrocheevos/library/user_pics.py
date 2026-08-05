"""User profile picture caching — mirrors `library/game_images.py`'s shape
(same confirmed base URL, `https://i.retroachievements.org`), reusing its
`build_image_url`/`download_image` directly since neither is actually
game-specific, just keyed by username instead of game id here.
"""

from pathlib import Path

from retrocheevos.library.game_images import build_image_url, download_image  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parents[3]
USER_PIC_CACHE_DIR = PROJECT_ROOT / "cache" / "user_pics"


def cached_user_pic_path(username: str) -> Path:
    """Where `username`'s profile photo lives locally, whether or not it's downloaded yet."""
    return USER_PIC_CACHE_DIR / f"{username}.png"
