"""ROM hashing (Architecture.md — Library layer).

Computes a whole-file MD5, which matches RetroAchievements' hash for many
simple/unheadered ROM formats. It will NOT match RA's hash on consoles with
special hashing rules (e.g. header-stripping on NES/N64, multi-track
handling on disc-based systems) — RA's real hasher (`RAHasher`) applies
per-console logic this does not replicate. Treat this as a first pass for
manual matching, not a complete implementation; revisit per-console before
relying on it for systems known to need special handling.
"""

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB — avoids loading a large ROM fully into memory


def compute_rom_hash(file_path: Path) -> str:
    """Whole-file MD5, lowercase hex."""
    digest = hashlib.md5()
    try:
        with open(file_path, "rb") as rom_file:
            while chunk := rom_file.read(CHUNK_SIZE):
                digest.update(chunk)
    except OSError:
        logger.exception("Failed to read ROM file %s", file_path)
        raise
    return digest.hexdigest()
