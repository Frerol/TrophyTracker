"""Library ownership must survive shared paths and session changes."""

import hashlib
import os
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import MIGRATIONS, apply_migrations, initialize_database
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.models.library import InstalledRom, RomFolder
from retrocheevos.services import credential_store, library_service as library, session_service


class LibraryAccountScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / 'library.db'
        real_create = db.create_connection
        self.real_create = real_create
        for patcher in (
            patch.object(db, 'create_connection', lambda database_path=None: real_create(self.database)),
            patch.object(credential_store, 'set_key', return_value=False),
            patch.object(credential_store, 'get_key', return_value=None),
            patch('retrocheevos.library.rahasher.is_available', return_value=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        initialize_database(self.database).close()
        self.a = session_service.add_account('A', 'fake-a')
        self.b = session_service.add_account('B', 'fake-b')
        self.romdir = self.root / 'roms'
        self.romdir.mkdir()
        with db.get_connection() as connection:
            connection.execute("INSERT INTO consoles (id, name) VALUES (5, 'GBA')")

    def _add_folder(self, account_id, path=None):
        with db.get_connection() as connection:
            return LibraryRepository(connection, account_id).add_rom_folder(
                RomFolder(path=str(path or self.romdir), console_id=5, watch_enabled=False)
            )

    def _roms(self, account_id):
        with db.get_connection() as connection:
            return LibraryRepository(connection, account_id).list_installed_roms()

    def test_same_paths_are_independent_and_upserts_preserve_history(self):
        for account_id in (self.a.id, self.b.id, None):
            folder = self._add_folder(account_id)
            self.assertEqual(self._add_folder(account_id).id, folder.id)
            with db.get_connection() as connection:
                repository = LibraryRepository(connection, account_id)
                rom = repository.add_installed_rom(InstalledRom(
                    file_path=str(self.romdir / 'game.gba'), hash='first', console_id=5
                ))
                repository.set_last_played(rom.id, datetime(2026, 1, 1))
                updated = repository.add_installed_rom(InstalledRom(
                    file_path=rom.file_path, hash='second', console_id=5
                ))
                self.assertEqual(updated.id, rom.id)
        ids = []
        for account_id in (self.a.id, self.b.id, None):
            roms = self._roms(account_id)
            self.assertEqual(len(roms), 1)
            self.assertEqual(roms[0].hash, 'second')
            self.assertEqual(roms[0].last_played_at, datetime(2026, 1, 1))
            ids.append(roms[0].id)
        self.assertEqual(len(set(ids)), 3)

    def test_scan_keeps_original_account_on_switch_and_logout(self):
        (self.romdir / 'game.gba').write_bytes(b'game')
        folder = self._add_folder(self.b.id)
        for change_session in (lambda: session_service.switch_account(self.a.id), session_service.logout):
            with self.subTest(change_session=change_session):
                session_service.switch_account(self.b.id)
                result = library.scan_rom_folder(folder.id, lambda *_: change_session())
                self.assertEqual(len(result.recorded), 1)
                self.assertEqual(len(self._roms(self.b.id)), 1)
                self.assertEqual(self._roms(self.a.id), [])
                self.assertEqual(self._roms(None), [])
                with db.get_connection() as connection:
                    LibraryRepository(connection, self.b.id).remove_installed_rom(result.recorded[0].id)

    def test_scan_all_keeps_owner_across_folders(self):
        other = self.root / 'other'
        other.mkdir()
        (self.romdir / 'first.gba').write_bytes(b'first')
        (other / 'second.gba').write_bytes(b'second')
        self._add_folder(self.b.id)
        self._add_folder(self.b.id, other)
        result = library.scan_all_rom_folders(lambda *_: session_service.switch_account(self.a.id))
        self.assertEqual(len(result.recorded), 2)
        self.assertEqual(len(self._roms(self.b.id)), 2)
        self.assertEqual(self._roms(self.a.id), [])

    def test_manual_scan_keeps_owner_during_hashing(self):
        path = self.romdir / 'manual.gba'
        path.write_bytes(b'manual')
        def change_during_hash(*_):
            session_service.switch_account(self.a.id)
            return 'hash'
        with patch.object(library, 'compute_rom_hash', side_effect=change_during_hash):
            library.scan_and_record_rom(str(path), 5)
        self.assertEqual(len(self._roms(self.b.id)), 1)
        self.assertEqual(self._roms(self.a.id), [])

    def test_rehash_keeps_original_owner(self):
        path = self.romdir / 'game.gba'
        path.write_bytes(b'new bytes')
        library.record_installed_rom(str(path), 5, 'old')
        library.rehash_installed_roms(lambda *_: session_service.switch_account(self.a.id))
        self.assertEqual(self._roms(self.b.id)[0].hash, hashlib.md5(b'new bytes').hexdigest())
        self.assertEqual(self._roms(self.a.id), [])

    def test_rehash_zip_retains_inner_rom_hash(self):
        path = self.romdir / 'game.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('nested/game.gba', b'inner ROM bytes')
        self._add_folder(self.b.id)
        library.scan_all_rom_folders()
        expected = hashlib.md5(b'inner ROM bytes').hexdigest()
        self.assertEqual(self._roms(self.b.id)[0].hash, expected)
        result = library.rehash_installed_roms()
        self.assertEqual(result.changed, 0)
        self.assertEqual(self._roms(self.b.id)[0].hash, expected)

    def test_manual_zip_scan_hashes_inner_rom(self):
        path = self.romdir / 'manual.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('game.gba', b'inner ROM bytes')
        rom = library.scan_and_record_rom(str(path), 5)
        self.assertEqual(rom.hash, hashlib.md5(b'inner ROM bytes').hexdigest())
        self.assertEqual(rom.file_path, str(path))

    def test_rehash_multifile_zip_preserves_container_handling(self):
        path = self.romdir / 'set.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('first.bin', b'first')
            archive.writestr('second.bin', b'second')
        expected = hashlib.md5(path.read_bytes()).hexdigest()
        library.record_installed_rom(str(path), 5, expected)
        self.assertEqual(library.rehash_installed_roms().changed, 0)
        self.assertEqual(self._roms(self.b.id)[0].hash, expected)

    def test_removing_account_preserves_other_accounts_shared_paths(self):
        for account in (self.a, self.b):
            session_service.switch_account(account.id)
            self._add_folder(account.id)
            library.record_installed_rom(str(self.romdir / 'game.gba'), 5, 'hash')
        session_service.remove_account(self.a.id)
        self.assertEqual(len(self._roms(self.b.id)), 1)
        with db.get_connection() as connection:
            self.assertEqual(len(LibraryRepository(connection, self.b.id).list_rom_folders()), 1)

    @unittest.skipIf(os.name == 'nt', 'Windows paths are case-insensitive')
    def test_rescan_discovers_distinct_case_sensitive_path(self):
        upper = self.romdir / 'Game.gba'
        lower = self.romdir / 'game.gba'
        upper.write_bytes(b'first')
        self._add_folder(self.b.id)
        library.scan_all_rom_folders()
        lower.write_bytes(b'second')
        if upper.samefile(lower):
            self.skipTest('filesystem is case-insensitive')
        result = library.scan_all_rom_folders()
        self.assertEqual(len(result.recorded), 1)
        self.assertEqual(len(self._roms(self.b.id)), 2)

    def test_v24_migration_preserves_existing_rows_and_history(self):
        old_path = self.root / 'old.db'
        connection = self.real_create(old_path)
        self.addCleanup(connection.close)
        for version, statements in MIGRATIONS:
            if version > 23:
                break
            for statement in statements:
                connection.execute(statement)
        connection.execute('PRAGMA user_version = 23')
        connection.execute("INSERT INTO accounts (id, username, api_key, is_active) VALUES (1, 'A', '', 1)")
        connection.execute("INSERT INTO consoles (id, name) VALUES (5, 'GBA')")
        repository = LibraryRepository(connection, 1)
        folder = repository.add_rom_folder(RomFolder(path='/roms', console_id=5, watch_enabled=True))
        rom = repository.add_installed_rom(InstalledRom(file_path='/roms/game.gba', hash='original', console_id=5))
        repository.set_last_played(rom.id, datetime(2026, 1, 1))
        connection.commit()
        apply_migrations(connection)
        self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], MIGRATIONS[-1][0])
        self.assertEqual(repository.get_rom_folder(folder.id).path, '/roms')
        self.assertEqual(repository.get_by_id(rom.id).hash, 'original')
        self.assertEqual(repository.get_by_id(rom.id).last_played_at, datetime(2026, 1, 1))
        connection.execute("INSERT INTO accounts (id, username, api_key, is_active) VALUES (2, 'B', '', 0)")
        other = LibraryRepository(connection, 2)
        self.assertNotEqual(other.add_rom_folder(RomFolder(path='/roms', console_id=5, watch_enabled=False)).id, folder.id)
        self.assertNotEqual(other.add_installed_rom(InstalledRom(file_path=rom.file_path, hash='other', console_id=5)).id, rom.id)
