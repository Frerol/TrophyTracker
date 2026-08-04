"""PSP disc image hashing (Architecture.md — Library layer).

RetroAchievements does not hash a PSP ISO's whole file. Its reference
hasher (`rc_hash_psp` in RAHasher/rcheevos) parses the ISO9660 filesystem to
locate `PSP_GAME/PARAM.SFO` and `PSP_GAME/SYSDIR/EBOOT.BIN`, then runs one
MD5 over both files' raw bytes back to back, each capped at 64 MiB. Source:
https://github.com/RetroAchievements/rcheevos/blob/develop/src/rhash/hash_disc.c
(`rc_hash_psp`, `rc_cd_find_file_sector`, `rc_hash_cd_file`).

Only plain ISO9660 images with 2048-byte sectors are handled — the layout
every common PSP ISO ripping tool produces. UMD is not CD-based, so the
2352/2336-byte raw-CD-sector modes RAHasher also supports for other discs
don't apply here and aren't implemented.

`.pbp` files are a different container (PARAM.SFO + executable + metadata
bundled together) and RA hashes those as a plain whole-file MD5 instead —
that case doesn't need this module; `hashing.compute_rom_hash` already
covers it via the generic whole-file path.

Directory lookups mirror `rc_cd_find_file_sector` exactly, including its
one quirk: only the root directory listing honors a directory record's
extent spanning multiple sectors (computed from the Primary Volume
Descriptor). Every subdirectory lookup below the root scans a single 2048
byte sector only, same as RAHasher — fine in practice since PSP_GAME and
SYSDIR only ever hold a handful of entries.
"""

import hashlib
import logging
from pathlib import Path
from typing import BinaryIO, Optional

logger = logging.getLogger(__name__)

SECTOR_SIZE = 2048
CHUNK_SIZE = 1024 * 1024  # 1 MiB — avoids loading a large entry fully into memory
MAX_HASHED_ENTRY_BYTES = 64 * 1024 * 1024  # RA's MAX_BUFFER_SIZE

# RetroAchievements' console ID is stored verbatim in `consoles.id` (Database.md
# 2.2), so this is stable — RA never reassigns an existing console's ID.
PSP_CONSOLE_ID = 41

_PARAM_SFO_PATH = ("PSP_GAME", "PARAM.SFO")
_EBOOT_BIN_PATH = ("PSP_GAME", "SYSDIR", "EBOOT.BIN")

_DirectoryEntry = tuple[int, int]  # (sector, size in bytes)


class NotAPspDiscError(Exception):
    """The file isn't a plain ISO9660 PSP UMD image RA's algorithm can hash."""


def compute_psp_iso_hash(file_path: Path) -> str:
    """RA-compatible hash for a PSP `.iso` dump. Raises `NotAPspDiscError` if
    the file isn't a recognizable PSP ISO9660 image, `OSError` on read failure.
    """
    with open(file_path, "rb") as rom_file:
        param_sfo = _find_entry(rom_file, _PARAM_SFO_PATH)
        if param_sfo is None:
            raise NotAPspDiscError(f"Not a PSP game disc: {file_path}")

        eboot_bin = _find_entry(rom_file, _EBOOT_BIN_PATH)
        if eboot_bin is None:
            raise NotAPspDiscError(f"Could not find primary executable in {file_path}")

        digest = hashlib.md5()
        _hash_entry(rom_file, param_sfo, digest)
        _hash_entry(rom_file, eboot_bin, digest)
        return digest.hexdigest()


def looks_like_psp_disc(file_path: Path) -> bool:
    """Cheap positive-identification check for Watch Folder auto-detection
    (`console_detection.py`) — true if `PSP_GAME/PARAM.SFO` is present, without
    hashing anything. Never raises: any read/parse failure just means "no".
    """
    try:
        with open(file_path, "rb") as rom_file:
            return _find_entry(rom_file, _PARAM_SFO_PATH) is not None
    except (OSError, NotAPspDiscError):
        return False


def _read_sector(rom_file: BinaryIO, sector: int) -> bytes:
    rom_file.seek(sector * SECTOR_SIZE)
    data = rom_file.read(SECTOR_SIZE)
    if len(data) < SECTOR_SIZE:
        raise NotAPspDiscError(f"Unexpected end of disc image while reading sector {sector}")
    return data


def _read_root_directory(rom_file: BinaryIO) -> _DirectoryEntry:
    """Primary Volume Descriptor lives at sector 16. Returns the root
    directory's (sector, sector_count) — the only lookup where RA computes
    a real sector count instead of assuming a single sector.
    """
    pvd = _read_sector(rom_file, 16)
    if pvd[1:6] != b"CD001":
        raise NotAPspDiscError("Not an ISO9660 image (missing CD001 signature at sector 16)")

    logical_block_size = pvd[128] | (pvd[129] << 8)
    root_record = pvd[156:190]  # 34-byte directory record embedded in the PVD
    sector = root_record[2] | (root_record[3] << 8) | (root_record[4] << 16)
    data_length = (
        root_record[10]
        | (root_record[11] << 8)
        | (root_record[12] << 16)
        | (root_record[13] << 24)
    )
    if logical_block_size == 0:
        num_sectors = 1
    else:
        num_sectors = -(-data_length // logical_block_size)  # ceil division
    return sector, num_sectors


def _scan_directory(
    rom_file: BinaryIO, dir_sector: int, num_sectors: int, name: str
) -> Optional[_DirectoryEntry]:
    """Scan one directory's extent for a child record named `name`
    (case-insensitive; ISO9660 file identifiers may carry a `;1` version
    suffix that directory names don't — both are accepted, matching
    `rc_cd_find_file_sector`).
    """
    target = name.encode("ascii").upper()
    sector = dir_sector
    remaining_sectors = num_sectors
    buffer = _read_sector(rom_file, sector)
    offset = 0

    while True:
        if offset >= len(buffer) or buffer[offset] == 0:
            remaining_sectors -= 1
            if remaining_sectors <= 0:
                return None
            sector += 1
            buffer = _read_sector(rom_file, sector)
            offset = 0
            continue

        record_length = buffer[offset]
        identifier_length = buffer[offset + 32]
        identifier = buffer[offset + 33 : offset + 33 + identifier_length]

        is_length_match = identifier_length == len(target)
        is_versioned_match = identifier_length > len(target) and identifier[
            len(target) : len(target) + 1
        ] == b";"
        if (is_length_match or is_versioned_match) and identifier[: len(target)].upper() == target:
            entry_sector = buffer[offset + 2] | (buffer[offset + 3] << 8) | (buffer[offset + 4] << 16)
            entry_size = (
                buffer[offset + 10]
                | (buffer[offset + 11] << 8)
                | (buffer[offset + 12] << 16)
                | (buffer[offset + 13] << 24)
            )
            return entry_sector, entry_size

        offset += record_length


def _find_entry(rom_file: BinaryIO, path_components: tuple[str, ...]) -> Optional[_DirectoryEntry]:
    if len(path_components) > 1:
        parent = _find_entry(rom_file, path_components[:-1])
        if parent is None:
            return None
        sector, _size = parent
        num_sectors = 1  # RA only computes a real extent size for the root lookup
    else:
        sector, num_sectors = _read_root_directory(rom_file)

    return _scan_directory(rom_file, sector, num_sectors, path_components[-1])


def _hash_entry(rom_file: BinaryIO, entry: _DirectoryEntry, digest: "hashlib._Hash") -> None:
    sector, size = entry
    remaining = min(size, MAX_HASHED_ENTRY_BYTES)
    rom_file.seek(sector * SECTOR_SIZE)
    while remaining > 0:
        chunk = rom_file.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            break
        digest.update(chunk)
        remaining -= len(chunk)
