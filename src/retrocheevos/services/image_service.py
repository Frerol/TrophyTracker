"""Game cover-art orchestration — combines `library/game_images.py` (pure
mechanics) with `models/game.Game` to decide whether a download is needed.
"""

import logging
from pathlib import Path
from typing import Optional

from retrocheevos.library.game_images import build_image_url, cached_image_path, download_image
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
