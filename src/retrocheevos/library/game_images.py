"""Game cover-art caching (Architecture.md — Library layer).

Pure mechanics only, mirrors `library/hashing.py`'s shape: where a cached
image lives (deterministic, no I/O) and how to fetch one (blocking network
call — the caller, `services/image_service.py`, is what decides *when* to
fetch, matching the API.md §5 "api/ doesn't decide when to refresh" split).

Base URL confirmed by the user: `https://i.retroachievements.org` + the
API's `ImageIcon` fragment (e.g. `/Images/012345.png`).
"""

import logging
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
    """Blocking fetch — call off the UI thread. Raises on failure; caller decides fallback."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        destination.write_bytes(response.content)
    except requests.RequestException:
        logger.exception("Failed to download game image from %s", url)
        raise
