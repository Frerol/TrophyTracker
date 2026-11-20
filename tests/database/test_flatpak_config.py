"""Upgrading a pre-Flatpak database preserves existing emulator settings."""

import sqlite3
import unittest

from retrocheevos.database.migrations import MIGRATIONS, apply_migrations
from retrocheevos.database.repositories.emulator_config_repository import EmulatorConfigRepository
from retrocheevos.models.emulator_config import EmulatorConfig


class FlatpakConfigMigrationTests(unittest.TestCase):
    def test_v24_upgrade_preserves_native_config_and_supports_flatpak_roundtrip(self) -> None:
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        for version, statements in MIGRATIONS:
            if version > 24:
                break
            for statement in statements:
                connection.execute(statement)
        connection.execute('PRAGMA user_version = 24')
        connection.execute("INSERT INTO consoles (id, name) VALUES (41, 'PSP')")
        connection.execute(
            'INSERT INTO emulator_configs (console_id, executable_path, arguments_template, core_path) '
            'VALUES (41, ?, ?, ?)', ('/apps/retroarch', '--fullscreen', '/cores/psp.so')
        )
        connection.commit()
        apply_migrations(connection)
        repository = EmulatorConfigRepository(connection)
        config = repository.get(41)
        self.assertEqual(config.executable_path, '/apps/retroarch')
        self.assertEqual(config.arguments_template, '--fullscreen')
        self.assertEqual(config.core_path, '/cores/psp.so')
        self.assertIsNone(config.flatpak_app_id)
        repository.upsert(EmulatorConfig(
            41, '/usr/bin/flatpak', flatpak_app_id='org.ppsspp.PPSSPP',
            flatpak_installation='system',
        ))
        self.assertEqual(repository.get(41).flatpak_app_id, 'org.ppsspp.PPSSPP')
        self.assertEqual(repository.list_all()[0].flatpak_installation, 'system')
        repository.upsert(EmulatorConfig(41, '/apps/PPSSPP.AppImage'))
        self.assertIsNone(repository.get(41).flatpak_app_id)
        self.assertIsNone(repository.get(41).flatpak_installation)
