"""Failure injection against real SQLite transactions and a fake vault."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from retrocheevos.database import connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.database.repositories.account_repository import AccountRepository
from retrocheevos.services import credential_store as store, session_service as sessions


class FailingCommitConnection(sqlite3.Connection):
    fail_commit = False

    def commit(self):
        if self.fail_commit:
            self.fail_commit = False
            raise sqlite3.OperationalError('injected commit failure')
        super().commit()


class AccountRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'app.db'
        initialize_database(self.path).close()
        self.connections = []
        self.fail_commit_on_open = False

        def connect(database_path=None):
            connection = sqlite3.connect(self.path, factory=FailingCommitConnection)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            connection.fail_commit = self.fail_commit_on_open
            self.connections.append(connection)
            return connection

        self.vault = {}
        self.backend = MagicMock()
        self.backend.get_password.side_effect = lambda service, username: self.vault.get(username)
        self.backend.set_password.side_effect = lambda service, username, key: self.vault.__setitem__(username, key)
        self.backend.delete_password.side_effect = lambda service, username: self.vault.pop(username, None)
        for patcher in (patch.object(db, 'create_connection', connect),
                        patch.object(store, 'keyring', self.backend),
                        patch.object(store, 'is_available', return_value=True),
                        patch.object(store, '_vacuum_away_freed_pages')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def rows(self, sql):
        connection = sqlite3.connect(self.path)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def test_activation_sql_failure_rolls_back_creation_and_leaves_vault_untouched(self):
        original = sessions.add_account('Original', 'old')
        with patch.object(AccountRepository, 'set_active', side_effect=sqlite3.OperationalError('injected')):
            with self.assertRaises(sqlite3.Error):
                sessions.add_account('New', 'new')
        self.assertEqual(self.rows('SELECT id,is_active FROM accounts'), [(original.id, 1)])
        self.assertNotIn('New', self.vault)

    def test_creation_commit_failure_does_not_touch_vault(self):
        self.fail_commit_on_open = True
        with self.assertRaises(sqlite3.Error):
            sessions.add_account('New', 'new')
        self.assertEqual(self.rows('SELECT username FROM accounts'), [])
        self.assertEqual(self.vault, {})

    def test_replacement_commit_failure_keeps_old_credential(self):
        sessions.add_account('User', 'old')
        self.fail_commit_on_open = True
        with self.assertRaises(sqlite3.Error):
            sessions.add_account('User', 'new')
        self.assertEqual(self.vault['User'], 'old')
        self.assertEqual(self.rows('SELECT api_key FROM accounts'), [('',)])

    def test_vault_failure_retains_durable_fallback_and_retries(self):
        with patch.object(store, 'set_key', return_value=False):
            sessions.add_account('User', 'new')
        self.assertEqual(self.rows('SELECT api_key FROM accounts'), [('new',)])
        store.migrate_plaintext_keys()
        self.assertEqual(self.vault['User'], 'new')
        self.assertEqual(self.rows('SELECT api_key FROM accounts'), [('',)])

    def test_scrub_sql_failure_keeps_fallback_after_vault_write(self):
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TRIGGER fail_scrub BEFORE UPDATE OF api_key ON accounts "
                           "WHEN NEW.api_key = '' BEGIN SELECT RAISE(ABORT,'injected'); END")
        connection.close()
        sessions.add_account('User', 'new')
        self.assertEqual(self.vault['User'], 'new')
        self.assertEqual(self.rows('SELECT api_key FROM accounts'), [('new',)])

    def test_scrub_commit_failure_keeps_fallback_after_vault_write(self):
        def set_key(username, key):
            self.vault[username] = key
            self.connections[-1].fail_commit = True
            return True
        with patch.object(store, 'set_key', side_effect=set_key):
            sessions.add_account('User', 'new')
        self.assertEqual(self.vault['User'], 'new')
        self.assertEqual(self.rows('SELECT api_key FROM accounts'), [('new',)])

    def test_removal_commit_failure_preserves_account_and_vault(self):
        account = sessions.add_account('User', 'old')
        self.fail_commit_on_open = True
        with self.assertRaises(sqlite3.Error):
            sessions.remove_account(account.id)
        self.assertEqual(self.rows('SELECT username FROM accounts'), [('User',)])
        self.assertEqual(self.vault['User'], 'old')
        self.assertEqual(self.rows('SELECT username FROM pending_credential_deletions'), [])

    def test_real_vault_delete_error_is_retryable_without_logging_secret(self):
        account = sessions.add_account('User', 'old')
        self.backend.delete_password.side_effect = RuntimeError('SECRET-DO-NOT-LOG')
        with self.assertLogs(level='WARNING') as captured:
            sessions.remove_account(account.id)
        self.assertNotIn('SECRET-DO-NOT-LOG', '\n'.join(captured.output))
        self.assertEqual(self.rows('SELECT username FROM accounts'), [])
        self.assertEqual(self.rows('SELECT username FROM pending_credential_deletions'), [('User',)])
        self.backend.delete_password.side_effect = lambda service, username: self.vault.pop(username, None)
        self.assertEqual(sessions.cleanup_pending_credentials(), 1)
        self.assertNotIn('User', self.vault)
        self.assertEqual(self.rows('SELECT username FROM pending_credential_deletions'), [])

    def test_unavailable_vault_keeps_pending_deletion(self):
        account = sessions.add_account('User', 'old')
        with patch.object(store, 'is_available', return_value=False):
            sessions.remove_account(account.id)
            self.assertEqual(sessions.cleanup_pending_credentials(), 0)
        self.assertEqual(self.rows('SELECT username FROM pending_credential_deletions'), [('User',)])
        self.assertEqual(sessions.cleanup_pending_credentials(), 1)

    def test_readded_username_cancels_old_deletion(self):
        account = sessions.add_account('User', 'old')
        # Model a crash immediately after the removal transaction commits.
        with db.get_connection() as connection:
            AccountRepository(connection).remove(account.id)
        sessions.add_account('User', 'replacement')
        self.assertEqual(sessions.cleanup_pending_credentials(), 0)
        self.assertEqual(self.vault['User'], 'replacement')
        self.assertEqual(self.rows('SELECT username FROM pending_credential_deletions'), [])

    def test_absent_vault_entry_counts_as_success(self):
        account = sessions.add_account('User', 'old')
        self.vault.clear()
        sessions.remove_account(account.id)
        self.assertEqual(self.rows('SELECT username FROM pending_credential_deletions'), [])
