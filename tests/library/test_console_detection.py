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


class FolderConsoleTieBreakerTests(unittest.TestCase):
    """`folder_console_id` breaks ties between an extension's candidates and
    does nothing else — the disc formats it exists for, and the four ways it
    must stay out of the way.
    """

    def _write(self, tmpdir: str, name: str, data: bytes = b"disc bytes") -> Path:
        path = Path(tmpdir) / name
        path.write_bytes(data)
        return path

    def test_chd_in_playstation_folder_resolves_to_playstation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "Crash Bandicoot.chd")

            result = detect_console(path, console_catalog.PLAYSTATION)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.PLAYSTATION)

    def test_iso_in_playstation_2_folder_resolves_to_playstation_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "Jak II.iso", b"not an iso9660 image" * 100)

            result = detect_console(path, console_catalog.PLAYSTATION_2)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.PLAYSTATION_2)

    def test_cue_and_bin_in_same_folder_both_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("Metal Gear Solid.cue", "Metal Gear Solid.bin"):
                result = detect_console(self._write(tmpdir, name), console_catalog.PLAYSTATION)
                self.assertEqual(result.console_id, console_catalog.PLAYSTATION, name)

    def test_folder_console_not_among_candidates_stays_ambiguous(self) -> None:
        """A `.chd` in a folder labelled Game Boy Advance: RA never hashes GBA
        from a disc image, so the label is wrong, not the extension.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "impossible.chd")

            result = detect_console(path, console_catalog.GAMEBOY_ADVANCE)

            self.assertFalse(result.is_confident)
            self.assertTrue(result.is_recognized)
            self.assertNotIn(console_catalog.GAMEBOY_ADVANCE, result.candidate_console_ids)

    def test_unknown_extension_stays_unrecognized(self) -> None:
        """`.rvz` is Dolphin's compressed GameCube/Wii container, which
        nothing here can decode yet. A folder labelled GameCube must not
        promote it into a whole-file MD5 that would never match anything —
        an unmatched ROM in the library is worse than an honest "unsupported
        format", because it looks like the scan worked.

        (`.cso` used to be this test's example. It is now decoded properly by
        `library.ciso`, which is the difference between a format being
        unsupported and merely unrecognized.)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "Super Mario Sunshine.rvz")

            result = detect_console(path, console_catalog.GAMECUBE)

            self.assertFalse(result.is_confident)
            self.assertFalse(result.is_recognized)

    def test_cso_in_a_psp_folder_needs_no_tie_breaking(self) -> None:
        """`.cso` resolves on its own now — the folder label is irrelevant to
        it, which is the point: recognition came from format support, not
        from guessing.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "LEGO Indiana Jones.cso")

            self.assertEqual(detect_console(path).console_id, console_catalog.PSP)
            self.assertEqual(
                detect_console(path, console_catalog.GAMECUBE).console_id,
                console_catalog.PSP,
            )

    def test_does_not_override_unambiguous_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "misfiled.gba")

            result = detect_console(path, console_catalog.SUPER_NINTENDO)

            self.assertEqual(result.console_id, console_catalog.GAMEBOY_ADVANCE)

    def test_psp_disc_content_beats_folder_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "Daxter.iso", _build_psp_iso(b"param sfo", b"eboot bin"))

            result = detect_console(path, console_catalog.PLAYSTATION_2)

            self.assertEqual(result.console_id, console_catalog.PSP)

    def test_ambiguous_zip_member_uses_folder_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "disc.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("disc.iso", b"not an iso9660 image at all" * 100)

            result = detect_console(path, console_catalog.PLAYSTATION_2)

            self.assertTrue(result.is_confident)
            self.assertEqual(result.console_id, console_catalog.PLAYSTATION_2)
            self.assertEqual(result.inner_member, "disc.iso")

    def test_no_folder_console_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "Crash Bandicoot.chd")

            self.assertFalse(detect_console(path).is_confident)
            self.assertFalse(detect_console(path, None).is_confident)


if __name__ == "__main__":
    unittest.main()
