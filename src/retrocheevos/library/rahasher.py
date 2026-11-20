"""RAHasher integration (Architecture.md — Library layer).

`hashing.py` computes a whole-file MD5 and says so in its own docstring: it
does not implement RA's per-console rules — header stripping on NES/N64,
track handling on disc systems, the executable-based hash PlayStation uses.
Every format added by hand needs its own decoder (`ciso.py` is one; CHD, RVZ
and the CD readers would each be another), and each one is a fresh chance to
disagree with RA by a byte and match nothing.

RAHasher is RetroAchievements' own command-line hasher, built from the same
`rcheevos/src/rhash` sources the site itself uses, so its answer is correct
by construction rather than by our reimplementation being careful enough.
When it is available this module is the hashing path; when it isn't, callers
fall back to `hashing.compute_rom_hash`.

Where the binary comes from
---------------------------
RAHasher is GPL-3.0 (RALibretro's COPYING); the optional Windows binary and
its license/source notice live under `tools/rahasher/`. `rcheevos` underneath
it is MIT. See `tools/rahasher/RAHasher-SOURCE.txt` for redistribution details.
This module finds the executable rather than assuming it was bundled:

1. `RETROCHEEVOS_RAHASHER` in the environment — an explicit override, and
   what the tests use.
2. `tools/rahasher/` inside the frozen bundle, or next to the running .exe.
3. `tools/rahasher/` under the project root, when running from source.
   Legacy `tools/` locations remain supported.
4. Anywhere on `PATH`.

Nothing here downloads it. An absent binary is a supported state, not an
error: the app keeps working with the built-in hashing it has always used.

Calling convention (RALibretro 1.8.3, `src/RAHasher.cpp`)
---------------------------------------------------------
    RAHasher <console_id> <file>

Prints the 32-character hash to stdout followed by a newline and exits 0. On
failure it exits 1, having written the reason to stderr. A console id is
always passed explicitly — the `?` auto-detect mode iterates every candidate
algorithm and prints *several* concatenated hashes with no separator, which
is unparseable, and `console_detection` has already decided the console by
the time anything gets here.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ENV_OVERRIDE = "RETROCHEEVOS_RAHASHER"
EXECUTABLE_NAME = "RAHasher.exe" if sys.platform == "win32" else "RAHasher"
BUNDLED_SUBDIRECTORY = "tools/rahasher"
LEGACY_SUBDIRECTORY = "tools"

_HASH_PATTERN = re.compile(r"^[0-9a-f]{32}$")
# A CHD or a dual-layer disc image is gigabytes of decompression before a hash
# comes out. Generous on purpose — the alternative to waiting is recording a
# ROM with no hash at all — but bounded, so a wedged child process can't hang
# a folder scan forever.
TIMEOUT_SECONDS = 600

# Windows would otherwise flash a console window for every single ROM in a
# folder scan, because the app itself is built with `console=False`.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class RaHasherError(Exception):
    """RAHasher ran but could not hash the file."""


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []

    override = os.environ.get(ENV_OVERRIDE)
    if override:
        candidates.append(Path(override))

    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidates.append(Path(bundled) / BUNDLED_SUBDIRECTORY / EXECUTABLE_NAME)
        candidates.append(Path(bundled) / LEGACY_SUBDIRECTORY / EXECUTABLE_NAME)
        # A onedir build puts `_internal/` beside the .exe; someone dropping
        # the binary in by hand will put it next to the .exe, not inside it.
        candidates.append(Path(sys.executable).parent / BUNDLED_SUBDIRECTORY / EXECUTABLE_NAME)
        candidates.append(Path(sys.executable).parent / LEGACY_SUBDIRECTORY / EXECUTABLE_NAME)
        candidates.append(Path(sys.executable).parent / EXECUTABLE_NAME)
    else:
        project_root = Path(__file__).resolve().parents[3]
        candidates.append(project_root / BUNDLED_SUBDIRECTORY / EXECUTABLE_NAME)
        candidates.append(project_root / LEGACY_SUBDIRECTORY / EXECUTABLE_NAME)

    found_on_path = shutil.which(EXECUTABLE_NAME)
    if found_on_path:
        candidates.append(Path(found_on_path))

    return candidates


def find_executable() -> Optional[Path]:
    """The RAHasher binary, or `None` if it isn't installed.

    Deliberately not cached: the whole point of the search order is that
    someone can drop the .exe next to the app and have it picked up, and a
    cached `None` from startup would mean a restart before that took effect.
    The cost is a handful of `os.path.exists` calls per ROM, against a
    subprocess that reads the entire file.
    """
    for candidate in _candidate_paths():
        if candidate.is_file():
            return candidate
    return None


def is_available() -> bool:
    return find_executable() is not None


def compute_hash(file_path: Path, console_id: int) -> str:
    """RA's own hash for `file_path`, treated as a `console_id` ROM.

    Raises `RaHasherError` if the binary is missing, times out, or reports
    failure. Callers decide whether that means falling back or skipping the
    file — this deliberately never returns a hash it isn't sure of, because
    a wrong hash is indistinguishable from a ROM RA simply doesn't know, and
    it lands in the database where it will be trusted later.
    """
    executable = find_executable()
    if executable is None:
        raise RaHasherError("RAHasher is not installed")

    try:
        completed = subprocess.run(
            [str(executable), str(console_id), str(file_path)],
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RaHasherError(f"RAHasher timed out after {TIMEOUT_SECONDS}s") from error
    except OSError as error:
        raise RaHasherError(f"Could not run {executable}: {error}") from error

    # Both streams are decoded leniently: RAHasher writes whatever the OS
    # handed it for a path, and a ROM filename with an unusual byte in it
    # must not turn into a decode error that looks like a hashing failure.
    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()

    if completed.returncode != 0:
        raise RaHasherError(stderr or f"RAHasher exited {completed.returncode}")

    # Exit code 0 with unparseable output means the contract changed under
    # us. Better to refuse than to store whatever the first 32 characters
    # happened to be.
    if not _HASH_PATTERN.match(stdout):
        raise RaHasherError(f"Unexpected RAHasher output: {stdout[:120]!r}")

    return stdout
