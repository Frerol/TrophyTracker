"""ROM hashing (Architecture.md — Library layer).

Two hashers, and the first one that can answer wins:

1. `library.rahasher` — RetroAchievements' own RAHasher binary, bundled in
   the Windows and Linux packages (and looked up on PATH from source). Correct for every format RA supports, including the CHD, CD
   and header-stripped cases below, because it *is* RA's implementation.
2. Everything in this module — the fallback for when it isn't installed.

The fallback computes a whole-file MD5, which matches RA for many simple
unheadered formats and will NOT match on consoles with special rules:
header-stripping on NES/N64, multi-track handling on disc systems, the
executable-based hash PlayStation uses. That gap is why the RAHasher path
exists; it is not a claim this module is finished.

GameCube and Wii discs in Dolphin's own containers (RVZ, WIA, GCZ) go
through `library.dolphin_hash`, which converts only the start of the disc
with Dolphin's `dolphin-tool` and hashes that with RAHasher.

PSP is the one disc case handled properly here, by `library.psp_hash` — both
`.iso` and (via `library.ciso`) `.cso`. `.pbp` files need nothing special;
RA hashes those as a plain whole file, same as the fallback below.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from retrocheevos.library import dolphin_hash, rahasher
from retrocheevos.library.psp_hash import PSP_CONSOLE_ID, NotAPspDiscError, compute_psp_iso_hash

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB — avoids loading a large ROM fully into memory
# `.cso` is the same disc as `.iso`, block-deflated; `psp_hash` inflates it on
# the fly and produces the identical hash. Falling through to the whole-file
# MD5 below would hash the *container* instead, which matches nothing.
_PSP_DISC_SUFFIXES = frozenset({".iso", ".cso"})


def compute_rom_hash(file_path: Path, console_id: Optional[int] = None) -> str:
    """RA-compatible hash for the given ROM file.

    Prefers RAHasher when it is installed and a console is known. Otherwise:
    whole-file MD5, except PSP disc images, which go through
    `psp_hash.compute_psp_iso_hash` and fall back to whole-file MD5 with a
    warning if the image doesn't parse, so scanning never hard-fails on an
    unexpected layout.

    A RAHasher *failure* falls through to the built-in path rather than
    propagating. RAHasher refusing a file usually means RA has no algorithm
    for it, and in that case the built-in answer is no worse than what this
    function returned before RAHasher existed — whereas raising would turn a
    single odd ROM into a scan that stops.
    """
    if console_id is not None and rahasher.is_available():
        try:
            return rahasher.compute_hash(file_path, console_id)
        except rahasher.RaHasherError as error:
            logger.warning(
                "RAHasher could not hash %s (console %s): %s — using built-in hashing",
                file_path,
                console_id,
                error,
            )

    if file_path.suffix.lower() in dolphin_hash.DOLPHIN_ONLY_SUFFIXES:
        # Dolphin's own containers. RAHasher cannot read them, but Dolphin can
        # convert the start of the disc, which is all the RA hash reads.
        if (
            dolphin_hash.can_hash(file_path, console_id)
            and rahasher.is_available()
            and dolphin_hash.is_available()
        ):
            try:
                return dolphin_hash.compute_hash(file_path, console_id, rahasher.compute_hash)
            except (dolphin_hash.DolphinHashError, rahasher.RaHasherError, OSError) as error:
                logger.warning("Could not hash %s through dolphin-tool: %s", file_path, error)
        # Otherwise keep the file in the library without inventing an RA hash
        # or reading GBs of compressed data for an MD5 that identifies nothing.
        logger.info("No compatible compressed-disc hasher for %s; manual matching available", file_path)
        return ""

    if console_id == PSP_CONSOLE_ID and file_path.suffix.lower() in _PSP_DISC_SUFFIXES:
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
