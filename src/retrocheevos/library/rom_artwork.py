"""Local artwork and GameTDB covers identified by Wii/GameCube disc IDs.

RVZ/WIA embed the original disc header at offset 0x58; no decompression is
needed. GameTDB's cover URL is also used by Dolphin's GameFile.cpp.
"""

import logging
import os
import re
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Optional

import requests
from PIL import Image

from retrocheevos import paths
from retrocheevos.library.rom_title import derive_title_from_filename
from retrocheevos.version import APP_VERSION

logger = logging.getLogger(__name__)
ROM_ART_CACHE = paths.cache_dir('rom_covers')
DISC_HEADER_OFFSET = 0x58
DISC_ID_SIZE = 6
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MISSING_COVER_TTL_SECONDS = 24 * 60 * 60
TRANSIENT_RETRY_SECONDS = 60
_LOCKS: dict[str, Lock] = {}
_LOCKS_GUARD = Lock()
_RETRY_AFTER: dict[str, float] = {}
REGIONS = {'E': 'US', 'P': 'EN', 'J': 'JA', 'K': 'KO', 'W': 'ZH',
           'D': 'DE', 'F': 'FR', 'I': 'IT', 'S': 'ES', 'H': 'NL', 'U': 'AU'}


def is_readable_image(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                return False
            image.verify()
        return True
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return False


def disc_id_for_rom(path: Path, console_id: int) -> Optional[str]:
    if console_id not in (16, 19):
        return None
    try:
        with path.open('rb') as source:
            if path.suffix.lower() in ('.rvz', '.wia'):
                header = source.read(DISC_HEADER_OFFSET + DISC_ID_SIZE)
                if header[:4] not in (b'RVZ\x01', b'WIA\x01'):
                    return None
                if int.from_bytes(header[0x48:0x4C], 'big') != {16: 1, 19: 2}[console_id]:
                    return None
                raw_id = header[DISC_HEADER_OFFSET:]
            elif path.suffix.lower() in ('.iso', '.gcm'):
                header = source.read(0x20)
                magic = header[0x18:0x1C] if console_id == 19 else header[0x1C:0x20]
                if magic != {19: b'\x5d\x1c\x9e\xa3', 16: b'\xc2\x33\x9f\x3d'}[console_id]:
                    return None
                raw_id = header[:DISC_ID_SIZE]
            else:
                return None
        disc_id = raw_id.decode('ascii')
        return disc_id if re.fullmatch(r'[A-Z0-9]{6}', disc_id) else None
    except (OSError, UnicodeError) as error:
        logger.debug('Could not read disc artwork ID from %s: %s', path, error)
        return None


def find_local_artwork(path: Path) -> Optional[Path]:
    stems = dict.fromkeys((path.stem, derive_title_from_filename(str(path))))
    for stem in stems:
        for directory in (path.parent, path.parent / 'covers', path.parent / 'images', path.parent / 'media/images'):
            for name in (stem, f'{stem}-image', f'{stem}-thumb', f'{stem}-cover'):
                for extension in ('.png', '.jpg', '.jpeg', '.webp'):
                    candidate = directory / (name + extension)
                    if candidate.is_file() and is_readable_image(candidate):
                        return candidate
    return None


def _dolphin_cached_cover(disc_id: str) -> Optional[Path]:
    cache_home = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    for directory in (
        cache_home / 'dolphin-emu/GameCovers',
        Path.home() / '.var/app/org.DolphinEmu.dolphin-emu/cache/dolphin-emu/GameCovers',
    ):
        candidate = directory / f'{disc_id}.png'
        if candidate.is_file() and is_readable_image(candidate):
            return candidate
    return None


def download_cover_image(url: str, destination: Path) -> bool:
    """Validate and atomically install a bounded image. False means HTTP 404."""
    with requests.get(url, timeout=(3, 8), stream=True,
                      headers={'User-Agent': f'Retrocheevos/{APP_VERSION}'}) as response:
        if response.status_code == 404:
            return False
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as target:
                temporary = Path(target.name)
                size = 0
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise ValueError('Cover image is too large')
                    target.write(chunk)
            if not is_readable_image(temporary):
                raise ValueError('Cover response is not a readable image')
            temporary.replace(destination)
            return True
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def ensure_disc_cover_cached(path: Path, console_id: int) -> Optional[Path]:
    disc_id = disc_id_for_rom(path, console_id)
    if disc_id is None:
        return None
    dolphin_cover = _dolphin_cached_cover(disc_id)
    if dolphin_cover is not None:
        return dolphin_cover
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(disc_id, Lock())
    with lock:
        destination = ROM_ART_CACHE / f'{disc_id}.png'
        if destination.is_file() and is_readable_image(destination):
            return destination
        missing = destination.with_suffix('.missing')
        try:
            if missing.is_file() and time.time() - missing.stat().st_mtime < MISSING_COVER_TTL_SECONDS:
                return None
            if time.monotonic() < _RETRY_AFTER.get(disc_id, 0):
                return None
            regions = dict.fromkeys((REGIONS.get(disc_id[3], 'EN'), 'EN', 'US'))
            for region in regions:
                url = f'https://art.gametdb.com/wii/cover/{region}/{disc_id}.png'
                if download_cover_image(url, destination):
                    missing.unlink(missing_ok=True)
                    logger.info('Cached GameTDB cover for %s', disc_id)
                    return destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            missing.touch()
        except (OSError, ValueError, requests.RequestException) as error:
            _RETRY_AFTER[disc_id] = time.monotonic() + TRANSIENT_RETRY_SECONDS
            logger.warning('Could not cache disc cover for %s: %s', disc_id, error)
        return None
