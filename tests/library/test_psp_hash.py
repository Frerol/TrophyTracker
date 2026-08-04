"""Tests for `library.psp_hash` against a synthetic ISO9660 image built
directly from the on-disc byte layout (independent of the parser under
test), so a match here means the parser reads the real ISO9660 format
correctly, not just its own encoding of it.
"""

import hashlib
import tempfile
import unittest
from pathlib import Path

from retrocheevos.library.psp_hash import NotAPspDiscError, compute_psp_iso_hash

SECTOR_SIZE = 2048


def _directory_record(identifier: bytes, lba: int, size: int, is_directory: bool) -> bytes:
    record = bytearray()
    record.append(0)  # length, filled in at the end
    record.append(0)  # extended attribute record length
    record += lba.to_bytes(4, "little") + lba.to_bytes(4, "big")
    record += size.to_bytes(4, "little") + size.to_bytes(4, "big")
    record += bytes(7)  # recording date/time, unused by the parser
    record.append(0x02 if is_directory else 0x00)  # file flags
    record.append(0)  # file unit size
    record.append(0)  # interleave gap size
    record += (1).to_bytes(2, "little") + (1).to_bytes(2, "big")  # volume sequence number
    record.append(len(identifier))
    record += identifier
    if len(identifier) % 2 == 0:
        record.append(0)  # padding to keep the record an even length
    record[0] = len(record)
    return bytes(record)


def _sectors_needed(size: int) -> int:
    return -(-size // SECTOR_SIZE)  # ceil division


def _build_psp_iso(param_sfo: bytes, eboot_bin: bytes) -> bytes:
    """Root (17) -> PSP_GAME (18) -> SYSDIR (19), with PARAM.SFO and
    EBOOT.BIN data placed after all three (fixed, single-sector) directory
    extents, each sized to fit the actual content instead of assuming it
    fits in one sector. File identifiers carry the ";1" ISO9660 version
    suffix real images use, to exercise that matching path too.
    """
    root_sector, psp_game_sector, sysdir_sector = 17, 18, 19
    param_sfo_sector = 20
    eboot_bin_sector = param_sfo_sector + _sectors_needed(len(param_sfo))

    root_dir = (
        _directory_record(b"\x00", root_sector, SECTOR_SIZE, True)
        + _directory_record(b"\x01", root_sector, SECTOR_SIZE, True)
        + _directory_record(b"PSP_GAME", psp_game_sector, SECTOR_SIZE, True)
    )
    psp_game_dir = (
        _directory_record(b"\x00", psp_game_sector, SECTOR_SIZE, True)
        + _directory_record(b"\x01", root_sector, SECTOR_SIZE, True)
        + _directory_record(b"PARAM.SFO;1", param_sfo_sector, len(param_sfo), False)
        + _directory_record(b"SYSDIR", sysdir_sector, SECTOR_SIZE, True)
    )
    sysdir_dir = (
        _directory_record(b"\x00", sysdir_sector, SECTOR_SIZE, True)
        + _directory_record(b"\x01", psp_game_sector, SECTOR_SIZE, True)
        + _directory_record(b"EBOOT.BIN;1", eboot_bin_sector, len(eboot_bin), False)
    )

    pvd = bytearray(SECTOR_SIZE)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[128:130] = (SECTOR_SIZE).to_bytes(2, "little")
    root_record = _directory_record(b"\x00", root_sector, len(root_dir), True)
    pvd[156 : 156 + len(root_record)] = root_record

    sectors = {
        16: bytes(pvd),
        root_sector: root_dir,
        psp_game_sector: psp_game_dir,
        sysdir_sector: sysdir_dir,
        param_sfo_sector: param_sfo,
        eboot_bin_sector: eboot_bin,
    }
    last_sector = eboot_bin_sector + _sectors_needed(len(eboot_bin))
    image = bytearray(SECTOR_SIZE * last_sector)
    for sector, content in sectors.items():
        start = sector * SECTOR_SIZE
        image[start : start + len(content)] = content
    return bytes(image)


class ComputePspIsoHashTests(unittest.TestCase):
    def test_matches_md5_of_param_sfo_and_eboot_bin_concatenated(self) -> None:
        param_sfo = b"PARAM.SFO test content" * 100
        eboot_bin = b"\x7fELF" + b"fake executable bytes" * 500
        expected = hashlib.md5(param_sfo + eboot_bin).hexdigest()

        with tempfile.TemporaryDirectory() as tmpdir:
            iso_path = Path(tmpdir) / "game.iso"
            iso_path.write_bytes(_build_psp_iso(param_sfo, eboot_bin))

            self.assertEqual(compute_psp_iso_hash(iso_path), expected)

    def test_raises_when_not_iso9660(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            garbage_path = Path(tmpdir) / "not_an_iso.iso"
            garbage_path.write_bytes(b"not a disc image" * 200)

            with self.assertRaises(NotAPspDiscError):
                compute_psp_iso_hash(garbage_path)

    def test_raises_when_param_sfo_missing(self) -> None:
        # A root directory with no PSP_GAME entry at all.
        root_dir = _directory_record(b"\x00", 17, SECTOR_SIZE, True) + _directory_record(
            b"\x01", 17, SECTOR_SIZE, True
        )
        pvd = bytearray(SECTOR_SIZE)
        pvd[0] = 1
        pvd[1:6] = b"CD001"
        pvd[128:130] = (SECTOR_SIZE).to_bytes(2, "little")
        root_record = _directory_record(b"\x00", 17, len(root_dir), True)
        pvd[156 : 156 + len(root_record)] = root_record

        image = bytearray(SECTOR_SIZE * 18)
        image[16 * SECTOR_SIZE : 16 * SECTOR_SIZE + SECTOR_SIZE] = pvd
        image[17 * SECTOR_SIZE : 17 * SECTOR_SIZE + len(root_dir)] = root_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            iso_path = Path(tmpdir) / "no_param_sfo.iso"
            iso_path.write_bytes(bytes(image))

            with self.assertRaises(NotAPspDiscError):
                compute_psp_iso_hash(iso_path)


if __name__ == "__main__":
    unittest.main()
