"""Console/name-based artwork from Libretro's public thumbnail catalog.

The platform list is discovered and cached rather than restricting the
lookup to a fixed list of supported console IDs. No API key is required.
"""

import difflib
import hashlib
import json
import logging
import re
import tempfile
import time
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional
from urllib.parse import quote

import requests

from retrocheevos import paths
from retrocheevos.library.rom_artwork import download_cover_image, is_readable_image
from retrocheevos.library.rom_title import derive_title_from_filename
from retrocheevos.version import APP_VERSION

logger = logging.getLogger(__name__)
API_URL = 'https://api.github.com'
RAW_URL = 'https://raw.githubusercontent.com/libretro-thumbnails/'
INDEX_CACHE = paths.cache_dir('thumbnail_catalog')
COVER_CACHE = paths.cache_dir('thumbnail_covers')
INDEX_TTL_SECONDS = 7 * 24 * 60 * 60
RETRY_SECONDS = 60
MAX_INDEX_BYTES = 16 * 1024 * 1024
FUZZY_THRESHOLD = 0.92
_INDEX_LOCK = Lock()
_COVER_LOCKS: dict[str, Lock] = {}
_RETRY_AFTER: dict[str, float] = {}

# Alternative names used by RA and Libretro for the same platform.
# Every other console uses its supplied name and the discovered platform list.
PLATFORM_ALIASES = {
    1: ('Sega - Mega Drive - Genesis',),
    8: ('NEC - PC Engine - TurboGrafx 16',),
    9: ('Sega - Mega-CD - Sega CD',),
    11: ('Sega - Master System - Mark III',),
    23: ('Magnavox - Odyssey2',),
    26: ('DOS',),
    27: ('MAME', 'FBNeo - Arcade Games'),
    30: ('Commodore - 64',),
    37: ('Amstrad - CPC',),
    43: ('The 3DO Company - 3DO', '3DO'),
    47: ('NEC - PC-88',),
    48: ('NEC - PC-98',),
    52: ('Sharp - X68000',),
    57: ('Fairchild - Channel F',),
    60: ('Nintendo - Game and Watch',),
    66: ('Thomson - MOTO',),
    81: ('Nintendo - Family Computer Disk System',),
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    if not value.isascii():
        # Ignore Latin accents without erasing Japanese and other scripts.
        value = ''.join(
            unicodedata.normalize('NFKD', char)[0]
            if 'LATIN' in unicodedata.name(char, '') else char
            for char in value
        )
    value = re.sub(r'(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])', ' ', value)
    return ' '.join(re.findall(r'[^\W_]+', value))


def _title_key(value: str) -> str:
    # Articles sometimes move to the end in No-Intro/Redump titles.
    value = derive_title_from_filename(value + '.png')
    return ' '.join(word for word in _normalize(value).split() if word not in {'the', 'a', 'an'})


def select_platforms(console_id: int, console_name: str, platforms: list[str]) -> list[str]:
    by_key = {_normalize(name): name for name in platforms}
    by_system_name = {_normalize(name.split(' - ', 1)[-1]): name for name in platforms}
    aliases = [
        by_key.get(_normalize(name)) or by_system_name.get(_normalize(name))
        for name in PLATFORM_ALIASES.get(console_id, ())
    ]
    aliases = list(dict.fromkeys(name for name in aliases if name))
    if aliases:
        return aliases
    wanted = _normalize(console_name)
    if not wanted:
        return []
    exact = by_key.get(wanted) or by_system_name.get(wanted)
    if exact is not None:
        return [exact]
    # Partial platform names can silently choose the wrong system: DS/3DS,
    # GB/GBC and Wii/Wii U must remain separate even if one index is absent.
    return []


@lru_cache(maxsize=16)
def _group_titles(filenames: tuple[str, ...]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for filename in filenames:
        groups[_title_key(Path(filename).stem)].append(filename)
    return groups


def select_cover(title: str, filenames: list[str]) -> Optional[str]:
    exact_filename = title + '.png'
    if exact_filename in filenames:
        return exact_filename
    groups = _group_titles(tuple(filenames))
    needle = _title_key(title)
    matches = groups.get(needle)
    if matches:
        return max(matches, key=lambda name: difflib.SequenceMatcher(None, title.casefold(), Path(name).stem.casefold()).ratio())
    if not needle:
        return None
    # Never blur numbered sequels or roman numerals into a different game.
    numbers = set(re.findall(r'\d+|\b(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\b', needle))
    candidates = []
    for key in groups:
        if set(re.findall(r'\d+|\b(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\b', key)) != numbers:
            continue
        ratio = difflib.SequenceMatcher(None, needle, key).ratio()
        if ratio >= FUZZY_THRESHOLD:
            candidates.append((ratio, key))
    candidates.sort(reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.03):
        return None
    return groups[candidates[0][1]][0]


def _api_get(url: str) -> Any:
    with requests.get(url, timeout=(3, 8), stream=True,
                      headers={'User-Agent': f'Retrocheevos/{APP_VERSION}',
                               'Accept': 'application/vnd.github+json'}) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_content(64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_INDEX_BYTES:
                raise ValueError('Thumbnail index is too large')
    return json.loads(content)


def _cached_json(cache_name: str, fetch: Callable[[], Any]) -> Any:
    with _INDEX_LOCK:
        cache = INDEX_CACHE / f'{cache_name}.json'
        stale = None
        try:
            stale = json.loads(cache.read_text(encoding='utf-8'))
            if time.time() - cache.stat().st_mtime < INDEX_TTL_SECONDS:
                return stale
        except (OSError, ValueError):
            pass
        key = str(cache)
        if time.monotonic() < _RETRY_AFTER.get(key, 0):
            return stale
        try:
            data = fetch()
            cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=cache.parent, delete=False) as target:
                    temporary = Path(target.name)
                    json.dump(data, target)
                temporary.replace(cache)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return data
        except (OSError, ValueError, requests.RequestException) as error:
            _RETRY_AFTER[key] = time.monotonic() + RETRY_SECONDS
            logger.warning('Could not update thumbnail index %s: %s', cache_name, error)
            return stale


def _repositories() -> list[dict[str, str]]:
    def fetch():
        platforms = []
        for page in range(1, 11):
            rows = _api_get(f'{API_URL}/orgs/libretro-thumbnails/repos?per_page=100&page={page}')
            if not isinstance(rows, list):
                raise ValueError('Invalid thumbnail repository list')
            for row in rows:
                name = row.get('name', '')
                branch = row.get('default_branch', 'master')
                if re.fullmatch(r'[A-Za-z0-9_.-]+', name):
                    platforms.append({'name': name.replace('_', ' '), 'repo': name, 'branch': branch})
            if len(rows) < 100:
                break
        return platforms
    rows = _cached_json('platforms', fetch)
    return [row for row in (rows or []) if isinstance(row, dict)
            and all(isinstance(row.get(key), str) for key in ('name', 'repo', 'branch'))]


def _filenames(platform: dict[str, str]) -> list[str]:
    repo, branch = platform['repo'], platform['branch']
    key = hashlib.sha256(f'{repo}/{branch}'.encode()).hexdigest()[:24]
    def fetch():
        prefix = f'{API_URL}/repos/libretro-thumbnails/{quote(repo, safe="")}/git/trees/'
        root = _api_get(prefix + quote(branch, safe=''))
        if not isinstance(root, dict):
            raise ValueError('Invalid thumbnail tree')
        folder = next((row for row in root.get('tree', [])
                       if row.get('path') == 'Named_Boxarts' and row.get('type') == 'tree'), None)
        if folder is None:
            return []
        tree = _api_get(prefix + quote(folder['sha'], safe=''))
        if tree.get('truncated'):
            raise ValueError('Thumbnail index was truncated')
        return sorted(row['path'] for row in tree.get('tree', [])
                      if row.get('type') == 'blob' and row.get('path', '').lower().endswith('.png')
                      and '/' not in row['path'] and '\\' not in row['path'])
    rows = _cached_json(key, fetch)
    return [name for name in (rows or []) if isinstance(name, str)]


def ensure_named_cover_cached(title: str, console_id: int, console_name: str) -> Optional[Path]:
    """Find artwork by title within the requested platform, with local caching."""
    repositories = {item['name']: item for item in _repositories()}
    for name in select_platforms(console_id, console_name, list(repositories)):
        platform = repositories[name]
        filename = select_cover(title, _filenames(platform))
        if filename is None:
            continue
        url = (RAW_URL + quote(platform['repo'], safe='') + '/'
               + quote(platform['branch'], safe='') + '/Named_Boxarts/' + quote(filename, safe=''))
        key = hashlib.sha256(url.encode()).hexdigest()[:24]
        destination = COVER_CACHE / f'{key}.png'
        with _INDEX_LOCK:
            lock = _COVER_LOCKS.setdefault(key, Lock())
        with lock:
            if destination.is_file() and is_readable_image(destination):
                return destination
            if time.monotonic() < _RETRY_AFTER.get(url, 0):
                continue
            try:
                if download_cover_image(url, destination):
                    logger.info('Cached Libretro artwork for %s (%s)', title, name)
                    return destination
            except (OSError, ValueError, requests.RequestException) as error:
                logger.warning('Could not download thumbnail for %s: %s', title, error)
            _RETRY_AFTER[url] = time.monotonic() + RETRY_SECONDS
    return None
