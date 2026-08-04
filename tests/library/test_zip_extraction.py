import tempfile
import unittest
import zipfile
from pathlib import Path

from retrocheevos.library.zip_extraction import (
    MAX_EXTRACTED_SIZE_BYTES,
    extract_member,
    find_single_rom_member,
)


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


class FindSingleRomMemberTests(unittest.TestCase):
    def test_returns_the_only_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "game.zip"
            _write_zip(zip_path, {"game.gba": b"rom bytes"})

            self.assertEqual(find_single_rom_member(zip_path), "game.gba")

    def test_returns_none_for_multiple_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "mameset.zip"
            _write_zip(zip_path, {"cf-01.bin": b"a", "cf-02.bin": b"b"})

            self.assertIsNone(find_single_rom_member(zip_path))

    def test_returns_none_for_empty_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "empty.zip"
            with zipfile.ZipFile(zip_path, "w"):
                pass

            self.assertIsNone(find_single_rom_member(zip_path))

    def test_ignores_directory_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "game.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(zipfile.ZipInfo("Roms/"), "")
                archive.writestr("Roms/game.gba", b"rom bytes")

            self.assertEqual(find_single_rom_member(zip_path), "Roms/game.gba")

    def test_returns_none_for_corrupted_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_zip = Path(tmpdir) / "not-a-zip.zip"
            fake_zip.write_bytes(b"this is not a zip file" * 10)

            self.assertIsNone(find_single_rom_member(fake_zip))

    def test_returns_none_for_oversized_declared_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "spoofed.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("game.iso", b"tiny actual content")
                # Spoof the declared uncompressed size on the entry we just wrote.
                archive.infolist()[0].file_size = MAX_EXTRACTED_SIZE_BYTES + 1

            self.assertIsNone(find_single_rom_member(zip_path))


class ExtractMemberTests(unittest.TestCase):
    def test_extracts_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "game.zip"
            _write_zip(zip_path, {"game.gba": b"rom bytes"})
            destination_dir = Path(tmpdir) / "out"

            extracted = extract_member(zip_path, "game.gba", destination_dir)

            self.assertEqual(extracted, destination_dir / "game.gba")
            self.assertEqual(extracted.read_bytes(), b"rom bytes")

    def test_flattens_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "game.zip"
            _write_zip(zip_path, {"Roms/SubFolder/game.gba": b"rom bytes"})
            destination_dir = Path(tmpdir) / "out"

            extracted = extract_member(zip_path, "Roms/SubFolder/game.gba", destination_dir)

            self.assertEqual(extracted, destination_dir / "game.gba")
            self.assertFalse((destination_dir / "Roms").exists())


if __name__ == "__main__":
    unittest.main()
