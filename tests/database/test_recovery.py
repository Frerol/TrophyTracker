"""Migration and backup recovery tests; every database is temporary."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrocheevos.database import backup, migrations
from retrocheevos.database.connection import create_connection


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'app.db'

    def old_database(self):
        with patch.object(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:26]):
            connection = migrations.initialize_database(self.path)
        self.addCleanup(connection.close)
        connection.execute("INSERT INTO accounts (id,username,api_key,is_active) VALUES (1,'User','synthetic-secret',1)")
        connection.execute("INSERT INTO consoles (id,name) VALUES (1,'Console')")
        connection.execute("INSERT INTO games (id,title,console_id) VALUES (1,'Game',1)")
        connection.execute("INSERT INTO installed_roms (file_path,console_id,game_id,account_id,hash) VALUES ('manual.rom',1,1,1,'manual')")
        connection.execute("INSERT INTO user_lists (account_id,game_id,list_type) VALUES (1,1,'backlog')")
        connection.execute("UPDATE installed_roms SET manual_match=1")
        connection.execute("INSERT INTO user_preferences VALUES (1,'theme','dark')")
        connection.commit()
        return connection

    def test_failed_migration_rolls_back_schema_data_and_version_then_retries(self):
        connection = self.old_database()
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        failure = (version + 1, ['CREATE TABLE partial (id INTEGER)',
                                  "UPDATE accounts SET username='Changed'", 'INVALID SQL'])
        with patch.object(migrations, 'MIGRATIONS', [(version, []), failure]):
            with self.assertRaises(sqlite3.Error):
                migrations.apply_migrations(connection)
        self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], version)
        self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone())
        self.assertEqual(connection.execute('SELECT username FROM accounts').fetchone()[0], 'User')
        migrations.apply_migrations(connection)
        self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], migrations.supported_database_version())

    def test_backup_failure_stops_upgrade(self):
        connection = self.old_database()
        with patch.object(backup, 'create_backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                migrations.apply_migrations(connection)
        self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 26)

    def test_newer_schema_rejected_and_failed_initialization_closed(self):
        connection = create_connection(self.path)
        connection.execute('PRAGMA user_version=999')
        with patch.object(migrations, 'create_connection', return_value=connection):
            with self.assertRaises(migrations.UnsupportedDatabaseVersionError):
                migrations.initialize_database(self.path)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')

    def test_upgrade_and_restore_keep_populated_data(self):
        connection = self.old_database()
        before = {table: [tuple(row) for row in connection.execute(f'SELECT * FROM {table}')]
                  for table in ('accounts', 'user_lists', 'installed_roms', 'user_preferences')}
        migrations.apply_migrations(connection)
        saved = backup.list_backups(self.root / 'backups')[0]
        target = self.root / 'restored.db'
        backup.restore_backup(saved, target)
        self.assertTrue(backup.verify_backup(target))
        restored = create_connection(target)
        try:
            for table, rows in before.items():
                self.assertEqual([tuple(row) for row in restored.execute(f'SELECT * FROM {table}')], rows)
            migrations.apply_migrations(restored)
            self.assertEqual(restored.execute('SELECT game_id FROM installed_roms').fetchone()[0], 1)
        finally:
            restored.close()

    def test_representative_populated_historical_schemas_upgrade_and_restore(self):
        for version in (1, 10, 20, 26, 27):
            with self.subTest(version=version):
                path = self.root / f'v{version}.db'
                with patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if m[0] <= version]):
                    connection = migrations.initialize_database(path)
                try:
                    connection.execute("INSERT INTO accounts(id,username,api_key,is_active) VALUES(1,'Example','synthetic',1)")
                    connection.execute("INSERT INTO consoles(id,name) VALUES(7,'NES')")
                    connection.execute("INSERT INTO games(id,title,console_id,has_achievements) VALUES(1,'Example',7,1)")
                    connection.execute("INSERT INTO user_lists(account_id,game_id,list_type) VALUES(1,1,'backlog')")
                    columns = {row[1] for row in connection.execute('PRAGMA table_info(installed_roms)')}
                    connection.execute("INSERT INTO installed_roms(file_path,console_id,game_id,hash) VALUES('example.nes',7,1,'abc')")
                    if 'account_id' in columns:
                        connection.execute('UPDATE installed_roms SET account_id=1')
                    if 'manual_match' in columns:
                        connection.execute('UPDATE installed_roms SET manual_match=1')
                    connection.commit()
                    migrations.apply_migrations(connection)
                    self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], migrations.supported_database_version())
                    self.assertEqual(connection.execute('SELECT username FROM accounts').fetchone()[0], 'Example')
                    self.assertEqual(connection.execute('SELECT game_id FROM user_lists').fetchone()[0], 1)
                    row = connection.execute('SELECT game_id,account_id,manual_match FROM installed_roms').fetchone()
                    self.assertEqual(tuple(row[:2]), (1, 1))
                    if 'manual_match' in columns:
                        self.assertEqual(row['manual_match'], 1)
                    saved = backup.create_backup(connection=connection)
                    restored_path = self.root / f'restored-v{version}.db'
                    backup.restore_backup(saved, restored_path)
                    self.assertTrue(backup.verify_backup(restored_path))
                    restored = migrations.initialize_database(restored_path)
                    restored.close()
                finally:
                    connection.close()

    def test_backups_do_not_collide_and_refuse_existing_destination(self):
        connection = self.old_database()
        with patch.object(backup, 'datetime') as clock:
            clock.now.return_value.strftime.return_value = 'same-second'
            first = backup.create_backup(connection=connection)
            connection.execute("UPDATE accounts SET username='New'")
            connection.commit()
            second = backup.create_backup(connection=connection)
        self.assertNotEqual(first, second)
        saved = sqlite3.connect(first)
        try:
            self.assertEqual(saved.execute('SELECT username FROM accounts').fetchone()[0], 'User')
        finally:
            saved.close()
        with self.assertRaises(FileExistsError):
            backup.create_backup(connection=connection, destination=first)
        with self.assertRaises(FileExistsError):
            backup.create_backup(connection=connection, destination=self.path)
        backup.prune_backups(first.parent, keep=1)
        self.assertEqual(len(backup.list_backups(first.parent)), 1)

    def test_backup_rejects_open_write_transaction_without_hanging(self):
        connection = self.old_database()
        connection.execute("UPDATE accounts SET username='Uncommitted'")
        with self.assertRaises(ValueError):
            backup.create_backup(connection=connection)
        connection.rollback()

    def test_portable_export_scrubs_credentials_and_pending_deletions(self):
        connection = self.old_database()
        migrations.apply_migrations(connection)
        connection.execute("INSERT INTO pending_credential_deletions VALUES ('Other','now')")
        connection.commit()
        exported = backup.export_database(connection=connection, destination=self.root / 'portable.db')
        portable = sqlite3.connect(exported)
        try:
            self.assertEqual(portable.execute('SELECT api_key FROM accounts').fetchone()[0], '')
            self.assertEqual(portable.execute('SELECT COUNT(*) FROM pending_credential_deletions').fetchone()[0], 0)
        finally:
            portable.close()
        self.assertNotIn(b'synthetic-secret', exported.read_bytes())
        self.assertEqual(connection.execute('SELECT api_key FROM accounts').fetchone()[0], 'synthetic-secret')

    def test_restore_over_existing_wal_database(self):
        connection = self.old_database()
        saved = backup.create_backup(connection=connection)
        connection.execute("UPDATE accounts SET username='Changed'")
        connection.commit()
        backup.restore_backup(saved, self.path)
        self.assertEqual(connection.execute('SELECT username FROM accounts').fetchone()[0], 'User')
