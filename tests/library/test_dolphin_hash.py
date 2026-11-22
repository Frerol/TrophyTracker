"""Dolphin-only disc formats hashed from a partial ISO (RVZ/WIA/GCZ)."""

import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from retrocheevos.library import dolphin_hash, hashing


def be32(value):
    return value.to_bytes(4, "big")


def put(image: bytearray, offset: int, data: bytes) -> None:
    if len(image) < offset + len(data):
        image.extend(b"\0" * (offset + len(data) - len(image)))
    image[offset:offset + len(data)] = data


def gamecube_image() -> tuple[bytearray, int]:
    image = bytearray(0x10000)
    put(image, 0x1C, bytes([0xC2, 0x33, 0x9F, 0x3D]))
    put(image, 0x2440 + 0x14, be32(0x1000) + be32(0))  # apploader body, trailer
    put(image, 0x420, be32(0x5000))  # main.dol offset
    table = bytearray(0xD8)
    table[0:4], table[0x90:0x94] = be32(0x6000), be32(0x100)  # code segment 0
    table[7 * 4:7 * 4 + 4], table[0x90 + 7 * 4:0x94 + 7 * 4] = be32(0x8000), be32(0x2000)  # data 0
    put(image, 0x5000, bytes(table))
    return image, 0xA000


def wii_image(encrypted: bool = True) -> tuple[bytearray, int]:
    image = bytearray(0x10000)
    put(image, 0x61, b"\0" if encrypted else b"\1")
    put(image, 0x40000, be32(2) + be32(0x40020 >> 2) + be32(0) * 6)
    put(image, 0x40020, be32(0x50000 >> 2) + be32(1) + be32(0x100000 >> 2) + be32(0))
    base = 0x100000
    put(image, base + 0x2A4, be32(0x208) + be32(0x2C0 >> 2))  # TMD size and offset
    if encrypted:
        put(image, base + 0x2B8, be32(0x120000 >> 2) + be32((3 * 0x8000) >> 2))
        return image, 0x120000 + 3 * 0x8000
    part = 0x200000
    put(image, base + 0x2B8, be32(part >> 2) + be32(0x100000 >> 2))
    put(image, part + 0x2440 + 0x14, be32(0x100) + be32(0))
    put(image, part + 0x420, be32(0x4000 >> 2))  # shifted by 2 on Wii
    table = bytearray(0xD8)
    table[0:4], table[0x90:0x94] = be32(0x8000 >> 2), be32(0x4000 >> 2)
    put(image, part + 0x4000, bytes(table))
    return image, part + 0x8000 + 0x4000


class BytesNeededTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "disc.iso"

    def check(self, image, console, expected):
        self.path.write_bytes(bytes(image[:0x1000]))
        with self.assertRaises(dolphin_hash._NotYetWritten):
            dolphin_hash.bytes_needed(self.path, console)
        self.path.write_bytes(bytes(image) + b"\0" * max(0, expected - len(image)))
        self.assertEqual(dolphin_hash.bytes_needed(self.path, console), expected)

    def test_gamecube_reads_header_apploader_and_main_dol(self):
        self.check(*gamecube_image()[:1], dolphin_hash.GAMECUBE_CONSOLE_ID, gamecube_image()[1])

    def test_encrypted_wii_reads_tmd_and_first_clusters_skipping_update(self):
        image, expected = wii_image(encrypted=True)
        self.check(image, dolphin_hash.WII_CONSOLE_ID, expected)

    def test_decrypted_wii_reads_the_game_partition_main_dol(self):
        image, expected = wii_image(encrypted=False)
        self.check(image, dolphin_hash.WII_CONSOLE_ID, expected)

    def test_other_consoles_are_rejected(self):
        self.path.write_bytes(b"\0" * 0x1000)
        with self.assertRaises(dolphin_hash.DolphinHashError):
            dolphin_hash.bytes_needed(self.path, 12)


FAKE_TOOL = '''#!{python}
import sys, time
args = sys.argv[1:]
source, output = args[args.index("-i") + 1], args[args.index("-o") + 1]
data = open(source, "rb").read()
if b"FAIL" in data[:4]:
    sys.exit(3)
with open(output, "wb") as handle:
    for start in range(0, len(data), 0x10000):
        handle.write(data[start:start + 0x10000])
        handle.flush()
        time.sleep(0.01)
'''


@unittest.skipIf(sys.platform == "win32", "POSIX process groups")
class ComputeHashTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        tool = self.root / "dolphin-tool"
        tool.write_text(FAKE_TOOL.format(python=sys.executable))
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
        for target, value in (
            ("_find_tool", ("native", str(tool))),
            ("_work_dir", self.work),
        ):
            patcher = mock.patch.object(dolphin_hash, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def rom(self, image: bytes, total: int) -> Path:
        path = self.root / "game.rvz"
        path.write_bytes(image + b"\x55" * (total - len(image)))
        return path

    def test_conversion_stops_once_the_hashed_region_is_written(self):
        image, needed = wii_image(encrypted=True)
        total = 8 * 1024 * 1024
        rom = self.rom(bytes(image), total)
        seen = {}

        def hash_iso(path, console):
            seen["size"] = path.stat().st_size
            seen["console"] = console
            return "abc123"

        started = time.monotonic()
        self.assertEqual(dolphin_hash.compute_hash(rom, 19, hash_iso), "abc123")
        self.assertLess(time.monotonic() - started, 5)
        self.assertGreaterEqual(seen["size"], needed)
        self.assertLess(seen["size"], total)
        self.assertEqual(seen["console"], 19)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_failure_and_cancellation_clean_up(self):
        rom = self.root / "bad.rvz"
        rom.write_bytes(b"FAIL" + b"\0" * 100)
        with self.assertRaises(dolphin_hash.DolphinHashError):
            dolphin_hash.compute_hash(rom, 19, lambda *_: "x")
        image, _needed = wii_image()
        rom = self.rom(bytes(image), 4 * 1024 * 1024)
        with self.assertRaises(dolphin_hash.DolphinHashError):
            dolphin_hash.compute_hash(rom, 19, lambda *_: "x", should_cancel=lambda: True)
        self.assertEqual(list(self.work.iterdir()), [])


class HashingIntegrationTests(unittest.TestCase):
    def test_dolphin_formats_use_dolphin_tool_only_when_available(self):
        path = Path("/roms/game.rvz")
        with mock.patch.object(hashing.rahasher, "is_available", return_value=True), \
             mock.patch.object(hashing.rahasher, "compute_hash",
                               side_effect=hashing.rahasher.RaHasherError("Not a supported Wii file")), \
             mock.patch.object(dolphin_hash, "is_available", return_value=True), \
             mock.patch.object(dolphin_hash, "compute_hash", return_value="b3a0") as compute:
            self.assertEqual(hashing.compute_rom_hash(path, 19), "b3a0")
            compute.assert_called_once()
            with mock.patch.object(dolphin_hash, "is_available", return_value=False):
                self.assertEqual(hashing.compute_rom_hash(path, 19), "")
            compute.side_effect = dolphin_hash.DolphinHashError("boom")
            self.assertEqual(hashing.compute_rom_hash(path, 19), "")
            # Not a Dolphin disc system: never handed to dolphin-tool.
            compute.reset_mock()
            self.assertEqual(hashing.compute_rom_hash(path, 12), "")
            compute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
