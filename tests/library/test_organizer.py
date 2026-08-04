import tempfile
import unittest
from pathlib import Path

from retrocheevos.library.organizer import move_rom, resolve_destination


class ResolveDestinationTests(unittest.TestCase):
    def test_builds_path_inside_destination_folder(self) -> None:
        destination_folder = Path("D:/Emulators/PSP/Games")
        destination = resolve_destination(destination_folder, Path("incoming/game.iso"))
        self.assertEqual(destination, destination_folder / "game.iso")

    def test_appends_suffix_on_collision_with_a_different_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            destination_folder = root / "SNES"
            destination_folder.mkdir()
            (destination_folder / "game.sfc").write_bytes(b"existing file, different content")

            new_file = root / "incoming" / "game.sfc"
            new_file.parent.mkdir()
            new_file.write_bytes(b"new file")

            destination = resolve_destination(destination_folder, new_file)

            self.assertEqual(destination, destination_folder / "game (2).sfc")

    def test_does_not_rename_when_colliding_with_itself(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            destination_folder = root / "SNES"
            destination_folder.mkdir()
            existing = destination_folder / "game.sfc"
            existing.write_bytes(b"content")

            destination = resolve_destination(destination_folder, existing)

            self.assertEqual(destination, existing)


class MoveRomTests(unittest.TestCase):
    def test_moves_file_and_creates_destination_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "game.gba"
            source.write_bytes(b"rom data")
            destination = root / "Game Boy Advance" / "game.gba"

            result = move_rom(source, destination)

            self.assertEqual(result, destination)
            self.assertTrue(destination.exists())
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"rom data")

    def test_is_a_no_op_when_already_at_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            existing = root / "game.gba"
            existing.write_bytes(b"rom data")

            result = move_rom(existing, existing)

            self.assertEqual(result, existing)
            self.assertTrue(existing.exists())


if __name__ == "__main__":
    unittest.main()
