import tempfile
import unittest
import zipfile
from pathlib import Path

from retrocheevos.library import console_catalog
from retrocheevos.library.console_detection import detect_console
from tests.library.test_psp_hash import _build_psp_iso


class DetectConsoleTests(unittest.TestCase):
    def test_unambiguous_extension_is_confident(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "game.gba"
            path.write_bytes(b"whatever")

            result = detect_console(path)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.GAMEBOY_ADVANCE)
            self.assertEqual(result.candidate_console_ids, ())

    def test_iso_with_psp_layout_is_confidently_psp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "game.iso"
            path.write_bytes(_build_psp_iso(b"param sfo content", b"eboot bin content"))

            result = detect_console(path)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.PSP)

    def test_iso_without_psp_layout_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "game.iso"
            path.write_bytes(b"not an iso9660 image at all" * 100)

            result = detect_console(path)

            self.assertFalse(result.is_confident)
            self.assertTrue(result.is_recognized)
            self.assertIn(console_catalog.PSP, result.candidate_console_ids)
            self.assertGreater(len(result.candidate_console_ids), 1)

    def test_unknown_extension_is_not_recognized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mystery.xyz"
            path.write_bytes(b"whatever")

            result = detect_console(path)

            self.assertFalse(result.is_confident)
            self.assertFalse(result.is_recognized)

    def test_single_file_zip_detects_by_inner_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "Coin Fall (World) (Aftermarket).zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("Coin Fall (World) (Aftermarket).gba", b"rom bytes")

            result = detect_console(path)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.GAMEBOY_ADVANCE)
            self.assertEqual(result.inner_member, "Coin Fall (World) (Aftermarket).gba")

    def test_single_file_zip_with_ambiguous_inner_extension_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "disc.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("disc.iso", b"not an iso9660 image at all" * 100)

            result = detect_console(path)

            self.assertFalse(result.is_confident)
            self.assertIn(console_catalog.PSP, result.candidate_console_ids)
            self.assertEqual(result.inner_member, "disc.iso")

    def test_multi_file_zip_falls_back_to_arcade(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mameset.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("cf-01.bin", b"a")
                archive.writestr("cf-02.bin", b"b")

            result = detect_console(path)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.ARCADE)
            self.assertIsNone(result.inner_member)

    def test_single_file_zip_with_unrecognized_inner_extension_falls_back_to_arcade(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mystery.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("readme.xyz", b"whatever")

            result = detect_console(path)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.ARCADE)
            self.assertIsNone(result.inner_member)


if __name__ == "__main__":
    unittest.main()
