"""ROM hashing (Architecture.md — Library layer).

Computes a whole-file MD5, which matches RetroAchievements' hash for many
simple/unheadered ROM formats. It will NOT match RA's hash on consoles with
special hashing rules (e.g. header-stripping on NES/N64, multi-track
handling on disc-based systems) — RA's real hasher (`RAHasher`) applies
per-console logic this does not replicate. Treat this as a first pass for
manual matching, not a complete implementation; revisit per-console before
relying on it for systems known to need special handling.

PSP (`.iso`) is the first disc-based exception, handled by `library.psp_hash`
(see that module for the algorithm and its source). `.pbp` files don't need
special handling — RA hashes those as a plain whole file too, same as the
fallback below.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from retrocheevos.library.psp_hash import PSP_CONSOLE_ID, NotAPspDiscError, compute_psp_iso_hash

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB — avoids loading a large ROM fully into memory


def compute_rom_hash(file_path: Path, console_id: Optional[int] = None) -> str:
    """RA-compatible hash for the given ROM file.

    Whole-file MD5 for most consoles/formats. For PSP `.iso` images, uses
    `psp_hash.compute_psp_iso_hash` instead (see that module) — falls back
    to whole-file MD5 with a warning if the file doesn't parse as a plain
    ISO9660 PSP disc, so scanning never hard-fails on an unexpected layout.
    """
    if console_id == PSP_CONSOLE_ID and file_path.suffix.lower() == ".iso":
        try:
            return compute_psp_iso_hash(file_path)
        except NotAPspDiscError as error:
            logger.warning(
                "PSP ISO hash fell back to whole-file MD5 for %s: %s", file_path, error
            )

    digest = hashlib.md5()
    try:
        with open(file_path, "rb") as rom_file:
            while chunk := rom_file.read(CHUNK_SIZE):
                digest.update(chunk)
    except OSError:
        logger.exception("Failed to read ROM file %s", file_path)
        raise
    return digest.hexdigest()
