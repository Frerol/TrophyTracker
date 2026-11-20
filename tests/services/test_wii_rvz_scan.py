"""Wii RVZ files must be playable library entries before catalog matching."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.library.console_detection import detect_console
from retrocheevos.models.library import InstalledRom, RomFolderScanResult
from retrocheevos.gui.pages.library_page import _describe_scan
from retrocheevos.services import library_service as library


def rvz_header(disc_type: int) -> bytes:
    return b'RVZ\x01' + bytes(0x48 - 4) + disc_type.to_bytes(4, 'big')


class WiiRvzScanTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.romdir = self.root / 'Emulation/roms/wii'
        self.romdir.mkdir(parents=True)
        real_create = db.create_connection
        for patcher in (
            patch.object(db, 'create_connection', lambda database_path=None: real_create(self.root / 'test.db')),
            patch('retrocheevos.library.rahasher.is_available', return_value=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        initialize_database(self.root / 'test.db').close()

    def test_tilde_wii_folder_discovers_nested_rvz_without_invalid_md5(self) -> None:
        (self.romdir / 'Super Mario Galaxy.rvz').write_bytes(rvz_header(2))
        nested = self.romdir / 'Subfolder'
        nested.mkdir()
        (nested / 'Another Game.RVZ').write_bytes(rvz_header(2))
        with patch.dict(os.environ, {'HOME': str(self.root), 'USERPROFILE': str(self.root)}):
            folder = library.add_rom_folder('~/Emulation/roms/wii', 19)
        result = library.scan_rom_folder(folder.id)
        self.assertEqual(len(result.recorded), 2)
        self.assertEqual(result.unrecognized_paths, [])
        self.assertTrue(all(rom.console_id == 19 and rom.hash == '' and rom.game_id is None for rom in result.recorded))
        self.assertEqual(len(library.list_installed_roms()), 2)
        self.assertEqual(library.scan_rom_folder(folder.id).already_known_count, 2)
        self.assertIn('not yet matched', _describe_scan(result))

    def test_discovery_progress_precedes_hashing_and_can_cancel(self) -> None:
        from retrocheevos.utils.cancellation import OperationCancelled

        rom = self.romdir / 'game.rvz'
        rom.write_bytes(rvz_header(2))
        folder = library.add_rom_folder(str(self.romdir), 19)
        progress = []

        def hash_file(path, *_args):
            self.assertTrue(any(current == str(path) for _, current in progress))
            return ''

        with patch.object(library, '_hash_in_place', side_effect=hash_file):
            result = library.scan_rom_folder(folder.id, lambda *args: progress.append(args))
        self.assertEqual(len(result.recorded), 1)
        self.assertEqual(progress[0], (0, str(self.romdir)))
        cancelled = False

        def cancel_on_discovery(count, _path):
            nonlocal cancelled
            cancelled = count > 0

        with patch.object(library, '_hash_in_place') as hash_rom:
            with self.assertRaises(OperationCancelled):
                library.scan_rom_folder(folder.id, cancel_on_discovery, lambda: cancelled)
            hash_rom.assert_not_called()

    def test_content_detects_wii_and_gamecube_before_folder_hint(self) -> None:
        path = self.romdir / 'game.rvz'
        for disc_type, expected, incorrect_hint in ((2, 19, 16), (1, 16, 19)):
            path.write_bytes(rvz_header(disc_type))
            self.assertEqual(detect_console(path).console_id, expected)
            self.assertEqual(detect_console(path, incorrect_hint).console_id, expected)
        path.write_bytes(b'invalid header')
        self.assertFalse(detect_console(path).is_confident)
        self.assertEqual(detect_console(path, 19).console_id, 19)

    def test_one_unreadable_file_does_not_discard_other_roms(self) -> None:
        (self.romdir / 'bad.rvz').write_bytes(rvz_header(2))
        (self.romdir / 'good.rvz').write_bytes(rvz_header(2))
        folder = library.add_rom_folder(str(self.romdir), 19)
        def hash_file(path, *_args):
            if path.name == 'bad.rvz':
                raise OSError('unreadable file')
            return ''
        with patch.object(library, '_hash_in_place', side_effect=hash_file):
            result = library.scan_rom_folder(folder.id)
        self.assertEqual(len(result.recorded), 1)
        self.assertEqual(len(result.failed_paths), 1)
        self.assertIn('could not be read', _describe_scan(result))

    def test_missing_folder_is_reported_instead_of_successful_empty_scan(self) -> None:
        folder = library.add_rom_folder(str(self.root / 'missing'), 19)
        with self.assertRaises(FileNotFoundError):
            library.scan_rom_folder(folder.id)
        result = library.scan_all_rom_folders()
        self.assertEqual(len(result.failed_folders), 1)
        self.assertIn('could not be scanned', _describe_scan(result))

    def test_media_mounts_and_configured_folder_names_do_not_hide_roms(self) -> None:
        root = self.root / 'media/Images'
        root.mkdir(parents=True)
        (root / 'Game.rvz').write_bytes(rvz_header(2))
        folder = library.add_rom_folder(str(root), 19)
        self.assertEqual(len(library.scan_rom_folder(folder.id).recorded), 1)
        self.assertEqual(library.purge_non_rom_entries(), 0)
        self.assertEqual(len(library.list_installed_roms()), 1)
