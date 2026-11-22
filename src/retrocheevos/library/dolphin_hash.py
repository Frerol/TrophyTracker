"""RetroAchievements hashes for Dolphin-only disc formats (RVZ, WIA, GCZ).

RAHasher cannot read Dolphin's compressed containers, but RetroAchievements'
GameCube and Wii hashes (rcheevos `rc_hash_gamecube` / `rc_hash_wii`) only
read the start of the disc: headers, partition metadata, and either main.dol
(GameCube, decrypted Wii) or the first 1,024 encrypted clusters of each game
partition (retail Wii) — a few hundred MB at most of a 1.4–8.5 GB image.

So `dolphin-tool` (native, or inside Dolphin's Flatpak) converts the image to
a plain ISO in a temporary file; this module watches the file grow, works out
from its own headers exactly how far rcheevos will read, stops the conversion
as soon as that much is written, hashes the partial ISO with RAHasher and
deletes it. Measured on a 4.7 GB Wii RVZ: about 1.3 s and ~300 MB written,
same hash as the full conversion.

`dolphin-tool` writes the ISO front to back, which is what makes the partial
file valid. The conversion runs in its own process session and, under
Flatpak, with `--die-with-parent`, so stopping it also stops the sandboxed
child — killing `flatpak run` alone left the conversion running.
"""

import logging
import os
import shutil
import signal
import subprocess
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from retrocheevos import paths
from retrocheevos.library.process_environment import host_process_environment

logger = logging.getLogger(__name__)

GAMECUBE_CONSOLE_ID = 16
WII_CONSOLE_ID = 19
DISC_CONSOLES = frozenset({GAMECUBE_CONSOLE_ID, WII_CONSOLE_ID})
DOLPHIN_ONLY_SUFFIXES = frozenset({".rvz", ".wia", ".gcz"})
DOLPHIN_FLATPAK_ID = "org.DolphinEmu.dolphin-emu"

POLL_SECONDS = 0.02
TIMEOUT_SECONDS = 180.0
STOP_GRACE_SECONDS = 3.0
# Prefer a RAM-backed directory (no SSD writes) when it has this much room.
RUNTIME_DIR_MIN_FREE = 768 * 1024 * 1024
WORK_DIR_NAME = "trophytracker-disc-hash"

# rcheevos constants (hash_disc.c)
_BASE_HEADER_SIZE = 0x2440
_MAX_HEADER_SIZE = 1024 * 1024
_DOL_TABLE_SIZE = 0xD8
_WII_MAIN_HEADER_SIZE = 0x80
_WII_REGION_CODE = 0x4E000
_WII_PARTITION_INFO = 0x40000
_WII_CLUSTER = 0x8000
_WII_CLUSTER_DATA = 0x7C00
_WII_MAX_CLUSTERS = 1024


class DolphinHashError(Exception):
    """The disc could not be hashed through dolphin-tool."""


class _NotYetWritten(Exception):
    """The partial ISO does not reach a byte the computation needs yet."""


# --- How far rcheevos reads ----------------------------------------------------

class _Reader:
    """Reads the partial ISO, refusing bytes not written yet, and records the
    furthest byte rcheevos would touch."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._size = path.stat().st_size if path.exists() else 0
        self.needed = 0

    def read(self, offset: int, size: int) -> bytes:
        end = offset + size
        self.needed = max(self.needed, end)
        if end > self._size:
            raise _NotYetWritten
        with open(self._path, "rb") as handle:
            handle.seek(offset)
            return handle.read(size)

    def touch(self, offset: int, size: int) -> None:
        """A range rcheevos hashes but whose content this module never inspects."""
        if size > 0:
            self.needed = max(self.needed, offset + size)

    def be32(self, offset: int) -> int:
        return int.from_bytes(self.read(offset, 4), "big")


def _nintendo_partition(reader: _Reader, part_offset: int, shift: int) -> None:
    """Mirror of `rc_hash_nintendo_disc_partition`."""
    body = reader.be32(part_offset + _BASE_HEADER_SIZE + 0x14)
    trailer = reader.be32(part_offset + _BASE_HEADER_SIZE + 0x18)
    header_size = min(_BASE_HEADER_SIZE + 0x20 + body + trailer, _MAX_HEADER_SIZE)
    reader.touch(part_offset, header_size)
    dol_offset = reader.be32(part_offset + 0x420) << shift
    table = reader.read(part_offset + dol_offset, _DOL_TABLE_SIZE)
    for index in range(18):
        offset = int.from_bytes(table[index * 4:index * 4 + 4], "big") << shift
        size = int.from_bytes(table[0x90 + index * 4:0x94 + index * 4], "big") << shift
        reader.touch(part_offset + offset, size)


def _wii_disc(reader: _Reader) -> None:
    """Mirror of `rc_hash_wii_disc`."""
    encrypted = reader.read(0x61, 1)[0] == 0
    reader.touch(0, _WII_MAIN_HEADER_SIZE)
    reader.touch(_WII_REGION_CODE, 4)
    info = [reader.be32(_WII_PARTITION_INFO + index * 4) for index in range(8)]
    partitions = []
    for group in range(0, 8, 2):
        table = info[group + 1] << 2
        for index in range(info[group]):
            partitions.append((reader.be32(table + index * 8), reader.be32(table + index * 8 + 4)))
    if not partitions:
        raise DolphinHashError("No Wii partitions found")
    for start, kind in partitions:
        if kind == 1:  # update partition, not hashed
            continue
        base = start << 2
        tmd_size = min(reader.be32(base + 0x2A4), _WII_CLUSTER_DATA)
        tmd_offset = reader.be32(base + 0x2A8) << 2
        reader.touch(base + tmd_offset, tmd_size)
        part_offset = reader.be32(base + 0x2B8) << 2
        part_size = reader.be32(base + 0x2BC) << 2
        if encrypted:
            clusters = min(part_size // _WII_CLUSTER, _WII_MAX_CLUSTERS)
            if clusters:
                # Each cluster's last read ends exactly at the next cluster.
                reader.touch(part_offset + (clusters - 1) * _WII_CLUSTER + 0x400, _WII_CLUSTER_DATA)
        else:
            _nintendo_partition(reader, part_offset & 0xFFFFFFFF, 2)


def bytes_needed(iso_path: Path, console_id: int) -> int:
    """How many leading bytes of the ISO RAHasher reads for `console_id`.

    Raises `_NotYetWritten` while the file is too short to tell.
    """
    reader = _Reader(iso_path)
    if console_id == GAMECUBE_CONSOLE_ID:
        _nintendo_partition(reader, 0, 0)
    elif console_id == WII_CONSOLE_ID:
        _wii_disc(reader)
    else:
        raise DolphinHashError(f"Console {console_id} is not a Dolphin disc system")
    return reader.needed


# --- dolphin-tool ------------------------------------------------------------------

@lru_cache(maxsize=1)
def _find_tool() -> Optional[tuple[str, str]]:
    native = shutil.which("dolphin-tool")
    if native:
        return ("native", native)
    flatpak = shutil.which("flatpak")
    if flatpak:
        try:
            installed = subprocess.run(
                [flatpak, "info", DOLPHIN_FLATPAK_ID], capture_output=True, timeout=5,
                env=host_process_environment(),
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            installed = False
        if installed:
            return ("flatpak", flatpak)
    return None


def is_available() -> bool:
    return _find_tool() is not None


def can_hash(file_path: Path, console_id: Optional[int]) -> bool:
    return console_id in DISC_CONSOLES and file_path.suffix.lower() in DOLPHIN_ONLY_SUFFIXES


def _work_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and Path(runtime).is_dir():
        try:
            if shutil.disk_usage(runtime).free >= RUNTIME_DIR_MIN_FREE:
                directory = Path(runtime) / WORK_DIR_NAME
                directory.mkdir(mode=0o700, exist_ok=True)
                return directory
        except OSError:
            pass
    directory = paths.cache_dir(WORK_DIR_NAME)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _command(tool: tuple[str, str], rom: Path, output: Path) -> list[str]:
    convert = ["convert", "-i", str(rom), "-o", str(output), "-f", "iso"]
    kind, executable = tool
    if kind == "native":
        return [executable, *convert]
    return [
        executable, "run", "--die-with-parent",
        f"--filesystem={rom.parent}:ro", f"--filesystem={output.parent}",
        "--command=dolphin-tool", DOLPHIN_FLATPAK_ID, *convert,
    ]


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.wait(STOP_GRACE_SECONDS)


def _wait_until_still(path: Path, settle: float = 0.25, limit: float = 5.0) -> None:
    """Make sure nothing keeps writing the file once the process is stopped."""
    deadline = time.monotonic() + limit
    last = path.stat().st_size if path.exists() else -1
    while time.monotonic() < deadline:
        time.sleep(settle)
        size = path.stat().st_size if path.exists() else -1
        if size == last:
            return
        last = size
    logger.warning("dolphin-tool output %s was still growing after it was stopped", path)


def compute_hash(
    rom: Path,
    console_id: int,
    hash_iso: Callable[[Path, int], str],
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
    timeout: float = TIMEOUT_SECONDS,
) -> str:
    """RetroAchievements hash of a Dolphin-only disc image, via a partial ISO.

    `hash_iso` is RAHasher (`rahasher.compute_hash`). Raises
    `DolphinHashError` when dolphin-tool is missing or fails.
    """
    tool = _find_tool()
    if tool is None:
        raise DolphinHashError("dolphin-tool is not available")
    output = _work_dir() / f"{uuid.uuid4().hex}.iso"
    started = time.monotonic()
    process = subprocess.Popen(
        _command(tool, rom, output), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True, env=host_process_environment(),
    )
    try:
        needed: Optional[int] = None
        while True:
            if should_cancel is not None and should_cancel():
                raise DolphinHashError("cancelled")
            if time.monotonic() - started > timeout:
                raise DolphinHashError(f"dolphin-tool took longer than {timeout:.0f} s")
            finished = process.poll() is not None
            try:
                needed = bytes_needed(output, console_id)
            except _NotYetWritten:
                needed = None
            size = output.stat().st_size if output.exists() else 0
            if needed is not None and size >= needed:
                break
            if finished:
                if process.returncode != 0:
                    raise DolphinHashError(f"dolphin-tool failed (exit {process.returncode})")
                if needed is None or size < needed:
                    raise DolphinHashError("The converted disc is shorter than its headers say")
                break
            time.sleep(POLL_SECONDS)
        _stop(process)
        _wait_until_still(output)
        result = hash_iso(output, console_id)
        logger.info(
            "Hashed %s through dolphin-tool: %d MiB converted in %.1f s",
            rom.name, needed // (1024 * 1024), time.monotonic() - started,
        )
        return result
    finally:
        _stop(process)
        try:
            output.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temporary disc image %s", output)
