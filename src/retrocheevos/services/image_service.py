"""Game cover-art and user-profile-photo orchestration — combines
`library/game_images.py`/`library/user_pics.py` (pure mechanics) with the
relevant id/path to decide whether a download is needed.
"""

import logging
from pathlib import Path
from typing import Optional

from retrocheevos.library.activity_icons import cached_activity_icon_path
from retrocheevos.library.game_images import build_image_url, cached_image_path, download_image
from retrocheevos.library.user_pics import cached_user_pic_path
from retrocheevos.models.game import Game

logger = logging.getLogger(__name__)


def ensure_game_image_cached(game: Game) -> Optional[Path]:
    """Local path to `game`'s cover art, downloading it first if not cached yet.

    Runs network I/O when the image isn't cached — call from a background
    thread, not the UI thread (CodingStandards' threading model). Returns
    `None` if the game has no known image or the download fails; callers
    show a placeholder in that case, never crash.
    """
    destination = cached_image_path(game.id)
    if destination.exists():
        return destination

    if not game.image_path:
        return None

    try:
        download_image(build_image_url(game.image_path), destination)
    except Exception:
        logger.warning("No cached image available for game %d", game.id)
        return None

    return destination


def ensure_user_pic_cached(username: str, user_pic_path: Optional[str]) -> Optional[Path]:
    """Local path to `username`'s profile photo, downloading it first if not
    cached yet. `user_pic_path` is `ProfileStats.user_pic_path` (synced by
    `sync_service.sync_profile`) — passed explicitly rather than looked up
    here, since it isn't part of the `Account` model itself.

    Runs network I/O when the photo isn't cached — call from a background
    thread, not the UI thread. Returns `None` if there's no known photo yet
    or the download fails; callers fall back to a placeholder, never crash.
    """
    destination = cached_user_pic_path(username)
    if destination.exists():
        return destination

    if not user_pic_path:
        return None

    try:
        download_image(build_image_url(user_pic_path), destination)
    except Exception:
        logger.warning("No cached profile photo available for %s", username)
        return None

    return destination


def ensure_activity_icon_cached(game_id: int, icon_path: Optional[str]) -> Optional[Path]:
    """Local path to a Recent Activity feed game icon, downloading it first
    if not cached yet. Separate from `ensure_game_image_cached` (which needs
    a local `Game` row) since feed entries can reference games the account
    never synced.

    Runs network I/O when the icon isn't cached — call from a background
    thread. Returns `None` if there's no known icon or the download fails;
    callers fall back to a placeholder, never crash.
    """
    destination = cached_activity_icon_path(game_id)
    if destination.exists():
        return destination

    if not icon_path:
        return None

    try:
        download_image(build_image_url(icon_path), destination)
    except Exception:
        logger.warning("No cached activity icon available for game %d", game_id)
        return None

    return destination
