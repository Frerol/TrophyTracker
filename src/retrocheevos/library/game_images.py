"""Game cover-art caching (Architecture.md — Library layer).

Pure mechanics only, mirrors `library/hashing.py`'s shape: where a cached
image lives (deterministic, no I/O) and how to fetch one (blocking network
call — the caller, `services/image_service.py`, is what decides *when* to
fetch, matching the API.md §5 "api/ doesn't decide when to refresh" split).

Base URL confirmed by the user: `https://i.retroachievements.org` + the
API's `ImageIcon` fragment (e.g. `/Images/012345.png`).
"""

import logging
import os
import sys
import time
import tempfile
from pathlib import Path

import requests

from retrocheevos import paths

logger = logging.getLogger(__name__)

IMAGE_CACHE_DIR = paths.cache_dir("images")
IMAGE_BASE_URL = "https://i.retroachievements.org"
DOWNLOAD_TIMEOUT_SECONDS = 10


def cached_image_path(game_id: int) -> Path:
    """Where `game_id`'s cover art lives locally, whether or not it's downloaded yet."""
    return IMAGE_CACHE_DIR / f"{game_id}.png"


def build_image_url(image_path_fragment: str) -> str:
    return f"{IMAGE_BASE_URL}{image_path_fragment}"


def download_image(url: str, destination: Path) -> None:
    """Blocking fetch — call off the UI thread. Raises on failure; caller decides fallback.

    Writes to a temporary file in the same directory and atomically replaces
    the destination, so an interrupted download can never leave a partial
    file behind at the shared cache path.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        fd, raw_temp = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
        )
        temp_path = Path(raw_temp)
        with os.fdopen(fd, "wb") as handle:
            handle.write(response.content)
            handle.flush()
            os.fsync(handle.fileno())
        # Windows can briefly deny replacement while another writer or a
        # reader holds the target. Keep publication atomic and bound retries;
        # real permission failures still propagate and clean the temp file.
        for attempt in range(5):
            try:
                os.replace(temp_path, destination)
                break
            except PermissionError as error:
                if (sys.platform != "win32" or getattr(error, "winerror", None) not in (5, 32, 33)
                        or attempt == 4):
                    raise
                time.sleep(0.01 * (attempt + 1))
        temp_path = None
    except Exception:
        logger.exception("Failed to download game image from %s", url)
        raise
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove temporary artwork %s", temp_path)
