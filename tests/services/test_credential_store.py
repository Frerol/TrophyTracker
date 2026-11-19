"""API keys belong in the OS vault, not in the database file.

These tests never touch the real Credential Manager — the vault is faked, so
the suite stays hermetic and leaves nothing behind on the machine running it.
Real-backend behaviour was verified separately against `WinVaultKeyring`.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import retrocheevos.database.connection as connection_module
from retrocheevos.services import credential_store


class FakeVault:
    """Stands in for keyring: a dict with the same three operations."""

    def __init__(self):
        self.entries = {}

    def get(self, username):
        return self.entries.get(username)

    def set(self, username, key):
        self.entries[username] = key
        return True

    def delete(self, username):
        self.entries.pop(username, None)


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        from retrocheevos.database.migrations import initialize_database

        self.path = Path(tempfile.mkdtemp()) / "keys.db"
        real_create = connection_module.create_connection
        patcher = patch.object(
            connection_module,
            "create_connection",
            lambda database_path=None: real_create(self.path),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.path).close()

        self.vault = FakeVault()
        for name, func in (
            ("is_available", lambda: True),
            ("get_key", self.vault.get),
            ("set_key", self.vault.set),
            ("delete_key", self.vault.delete),
        ):
            p = patch.object(credential_store, name, func)
            p.start()
            self.addCleanup(p.stop)

    def _column(self, username):
        with connection_module.get_connection() as conn:
            row = conn.execute(
                "SELECT api_key FROM accounts WHERE username = ?", (username,)
            ).fetchone()
        return None if row is None else row["api_key"]

    def test_new_account_key_never_reaches_the_column(self):
        from retrocheevos.services import session_service

        session_service.add_account("Someone", "K" * 32)
        self.assertEqual(self._column("Someone"), "")
        self.assertEqual(self.vault.get("Someone"), "K" * 32)

    def test_account_is_hydrated_from_the_vault(self):
        from retrocheevos.services import session_service

        session_service.add_account("Someone", "K" * 32)
        account = session_service.get_active_account()
        self.assertEqual(account.api_key, "K" * 32)

    def test_plaintext_migration_moves_and_clears(self):
        with connection_module.get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (username, api_key, is_active) VALUES (?,?,0)",
                ("Legacy", "L" * 32),
            )
        self.assertEqual(credential_store.migrate_plaintext_keys(), 1)
        self.assertEqual(self._column("Legacy"), "")
        self.assertEqual(self.vault.get("Legacy"), "L" * 32)

    def test_migration_is_idempotent(self):
        with connection_module.get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (username, api_key, is_active) VALUES (?,?,0)",
                ("Legacy", "L" * 32),
            )
        credential_store.migrate_plaintext_keys()
        self.assertEqual(credential_store.migrate_plaintext_keys(), 0)

    def test_a_failed_vault_write_keeps_the_key(self):
        """Losing the key entirely is far worse than storing it in the clear.
        If the vault refuses, the column keeps it."""
        from retrocheevos.services import session_service

        with patch.object(credential_store, "set_key", lambda _u, _k: False):
            session_service.add_account("NoVault", "N" * 32)
        self.assertEqual(self._column("NoVault"), "N" * 32)

    def test_migration_leaves_the_key_when_the_vault_refuses(self):
        with connection_module.get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (username, api_key, is_active) VALUES (?,?,0)",
                ("Legacy", "L" * 32),
            )
        with patch.object(credential_store, "set_key", lambda _u, _k: False):
            self.assertEqual(credential_store.migrate_plaintext_keys(), 0)
        self.assertEqual(self._column("Legacy"), "L" * 32)

    def test_removing_an_account_deletes_its_vault_entry(self):
        from retrocheevos.services import session_service

        account = session_service.add_account("Someone", "K" * 32)
        self.assertIn("Someone", self.vault.entries)
        session_service.remove_account(account.id)
        self.assertNotIn("Someone", self.vault.entries)

    def test_new_key_wins_when_vault_update_fails(self):
        from retrocheevos.services import session_service

        session_service.add_account("Someone", "O" * 32)
        with patch.object(credential_store, "set_key", return_value=False):
            session_service.add_account("Someone", "N" * 32)
        self.assertEqual(self.vault.get("Someone"), "O" * 32)
        self.assertEqual(session_service.get_active_account().api_key, "N" * 32)
        # Once the vault accepts writes, startup migration reconciles it.
        self.assertEqual(credential_store.migrate_plaintext_keys(), 1)
        self.assertEqual(self._column("Someone"), "")
        self.assertEqual(self.vault.get("Someone"), "N" * 32)
        self.assertEqual(session_service.get_active_account().api_key, "N" * 32)


if __name__ == "__main__":
    unittest.main()
