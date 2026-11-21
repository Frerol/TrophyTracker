"""Game cover-art and user-profile-photo orchestration — combines
`library/game_images.py`/`library/user_pics.py` (pure mechanics) with the
relevant id/path to decide whether a download is needed.
"""

from concurrent.futures import Future
import logging
from threading import Lock
import sqlite3
from pathlib import Path
from typing import Optional

from retrocheevos.library.activity_icons import cached_activity_icon_path, cached_badge_image_path
from retrocheevos.library.game_images import build_image_url, cached_image_path, download_image
from retrocheevos.library.user_pics import cached_user_pic_path
from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom
from retrocheevos.library.local_covers import cached_local_cover_path
from retrocheevos.library.rom_artwork import (
    ensure_disc_cover_cached, find_local_artwork, is_readable_image,
)
from retrocheevos.library.thumbnail_catalog import ensure_named_cover_cached
from retrocheevos.library.rom_title import derive_title_from_filename
from retrocheevos.core.console_reference import CONSOLE_NAMES
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.console_repository import ConsoleRepository

logger = logging.getLogger(__name__)


# All page instances share the same disk destination. Only the owner does I/O;
# concurrent callers receive its result (including failure), then may retry.
_game_image_lock = Lock()
_game_image_flights: dict[Path, Future[Optional[Path]]] = {}


def ensure_game_image_cached(game: Game) -> Optional[Path]:
    """Cache artwork off the GUI thread, sharing work across concurrent callers."""
    destination = cached_image_path(game.id)
    with _game_image_lock:
        future = _game_image_flights.get(destination)
        owner = future is None
        if owner:
            future = Future()
            _game_image_flights[destination] = future
    if not owner:
        return future.result()
    try:
        result = _ensure_game_image_cached(game)
        future.set_result(result)
        return result
    except BaseException as error:
        future.set_exception(error)
        raise
    finally:
        with _game_image_lock:
            _game_image_flights.pop(destination, None)


def _ensure_game_image_cached(game: Game) -> Optional[Path]:
    """Local path to `game`'s cover art, downloading it first if not cached yet.

    Runs network I/O when the image isn't cached — call from a background
    thread, not the UI thread (CodingStandards' threading model). Returns
    `None` if the game has no known image or the download fails; callers
    show a placeholder in that case, never crash.
    """
    destination = cached_image_path(game.id)
    if destination.is_file() and is_readable_image(destination):
        return destination

    if game.image_path:
        try:
            download_image(build_image_url(game.image_path), destination)
        except Exception:
            logger.warning("No cached RA image available for game %d", game.id)
        if is_readable_image(destination):
            return destination
    return _named_rom_cover(game.title, game.console_id)


def _named_rom_cover(title: str, console_id: int) -> Optional[Path]:
    console_name = CONSOLE_NAMES.get(console_id)
    if console_name is None:
        # Newly added platforms can use the synced console's name without
        # requiring a release containing another hardcoded ID mapping.
        try:
            with get_connection() as connection:
                console = ConsoleRepository(connection).get_by_id(console_id)
                console_name = console.name if console else None
        except sqlite3.Error:
            logger.warning("Could not read the console name for artwork lookup")
    if not console_name:
        return None
    return ensure_named_cover_cached(title, console_id, console_name)


def ensure_rom_image_cached(rom: InstalledRom, cover_game: Optional[Game] = None) -> Optional[Path]:
    """Artwork independently of RA matching; user-picked covers always win.

    All disk/network work runs on the image loader's background pool.
    """
    manual = cached_local_cover_path(rom.id)
    if manual.is_file() and is_readable_image(manual):
        return manual
    local = find_local_artwork(Path(rom.file_path))
    if local is not None:
        return local
    disc_cover = ensure_disc_cover_cached(Path(rom.file_path), rom.console_id)
    if disc_cover is not None:
        return disc_cover
    named_cover = _named_rom_cover(derive_title_from_filename(rom.file_path), rom.console_id)
    if named_cover is not None:
        return named_cover
    return ensure_game_image_cached(cover_game) if cover_game is not None else None


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


def ensure_badge_image_cached(image_path: Optional[str]) -> Optional[Path]:
    """Local path to an award image (Awards view), downloading it first if
    needed. Same contract as `ensure_activity_icon_cached`: background thread
    only; `None` when there is no image or the download fails."""
    if not image_path or not Path(image_path).name:
        return None
    destination = cached_badge_image_path(image_path)
    if destination.exists():
        return destination
    try:
        download_image(build_image_url(image_path), destination)
    except Exception:
        logger.warning("No cached award image available for %s", image_path)
        return None
    return destination
