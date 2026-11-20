"""API keys, held by the OS credential vault instead of by the database.

On Windows that is Credential Manager (`WinVaultKeyring`), which encrypts
entries against the logged-in user account. The database previously held the
key as plain text, protected by nothing but NTFS permissions on the file —
anyone who could read `retrocheevos.db` had the key, and a copied or
backed-up database carried it along.

**Graceful degradation is deliberate.** `keyring` resolves a backend at
runtime and there is no guarantee one exists — a locked-down machine, a
stripped build, a platform without a vault. If the vault cannot be used, the
key stays in the database column and the app keeps working, loudly logged.
Refusing to start because a *storage improvement* is unavailable would be a
worse failure than the one being fixed.

That means `accounts.api_key` is still read and written as a fallback. It is
not dead: it is the second half of this design.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Shows up in Credential Manager as "Retrocheevos" under Generic Credentials,
# one entry per RetroAchievements username.
SERVICE_NAME = "Retrocheevos"

try:  # pragma: no cover - depends on the machine, not on the code
    import keyring
    from keyring.errors import KeyringError
except Exception as error:  # noqa: BLE001 — any import problem means "no vault"
    keyring = None
    KeyringError = Exception
    logger.warning("Credential vault unavailable (%s); API keys stay in the database", error)


def is_available() -> bool:
    """Can the OS vault actually be used right now?

    Checks for a usable backend, not just that the import worked: `keyring`
    installs a `fail.Keyring` placeholder when it finds no real backend, and
    that one raises on every call.
    """
    if keyring is None:
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:  # noqa: BLE001
        return False
    return "fail" not in type(backend).__module__.lower()


def get_key(username: str) -> Optional[str]:
    if not is_available():
        return None
    try:
        return keyring.get_password(SERVICE_NAME, username)
    except KeyringError as error:
        logger.warning("Could not read the key for %s from the vault: %s", username, error)
        return None


def set_key(username: str, api_key: str) -> bool:
    """Store `api_key`. Returns whether it actually landed in the vault —
    the caller needs to know, because clearing the database copy is only safe
    if it did."""
    if not is_available():
        return False
    try:
        keyring.set_password(SERVICE_NAME, username, api_key)
        return True
    except KeyringError:
        logger.warning("Could not store the key for %s in the vault", username)
        return False


def migrate_plaintext_keys() -> int:
    """Move any keys still sitting in `accounts.api_key` into the vault.

    Run at startup and after account changes. Not a schema migration: those are pure SQL and this
    needs the OS vault, which can fail per-machine in ways `PRAGMA
    user_version` has no way to express — a database marked "migrated" on a
    machine where the vault was unavailable would never retry.

    The column is only blanked for keys the vault confirmed it stored. A
    partial run is safe and simply resumes next launch.

    Returns how many keys were moved.
    """
    if not is_available():
        logger.info("Credential vault unavailable; leaving API keys in the database")
        return 0

    # Imported here, not at module scope: `database.repositories` imports
    # this module, so a top-level import would be circular.
    from retrocheevos.database.connection import get_connection

    moved = 0
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT id, username, api_key FROM accounts WHERE api_key IS NOT NULL AND api_key != ''"
        ).fetchall()
        for row in rows:
            if not set_key(row["username"], row["api_key"]):
                logger.warning(
                    "Could not move %s's key to the vault; leaving it in place",
                    row["username"],
                )
                continue
            connection.execute(
                "UPDATE accounts SET api_key = '' WHERE id = ?", (row["id"],)
            )
            moved += 1

    if moved:
        _vacuum_away_freed_pages()
        logger.info("Moved %d API key(s) from the database into the OS vault", moved)
    return moved


def _vacuum_away_freed_pages() -> None:
    """Rewrite the database file so the old plaintext keys are really gone.

    `UPDATE ... SET api_key = ''` clears the *value*; it does not overwrite
    the bytes. SQLite leaves the old row content in freed pages until
    something reuses them, so the key can still be read straight out of the
    file with a hex editor — which would make this whole change cosmetic.

    Runs once, only after a migration actually moved something, and outside
    any transaction because VACUUM cannot run inside one.
    """
    from retrocheevos.database.connection import create_connection

    connection = create_connection()
    try:
        connection.isolation_level = None  # autocommit; VACUUM needs it
        connection.execute("VACUUM")
    except Exception as error:  # noqa: BLE001 — the keys are already safe by now
        logger.warning("Could not vacuum the database after migrating keys: %s", error)
    finally:
        connection.close()


def delete_key(username: str) -> bool:
    """Return success only when deletion is confirmed; failures remain retryable.

    Called after account removal commits. An absent entry is already clean.
    Do not log backend exception text, which may contain credentials.
    """
    if not is_available():
        return False
    try:
        if keyring.get_password(SERVICE_NAME, username) is not None:
            keyring.delete_password(SERVICE_NAME, username)
        return True
    except Exception:
        logger.warning("Could not delete vault entry for %s; cleanup deferred", username)
        return False
