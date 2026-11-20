"""Versioned schema migrations, tracked via SQLite's `PRAGMA user_version`."""

import logging
import sqlite3
from pathlib import Path

from retrocheevos.database import backup as backup_module
from retrocheevos.database.connection import DEFAULT_DATABASE_PATH, create_connection
from retrocheevos.database.schema import (
    ALTER_TABLES_V7,
    ALTER_TABLES_V8,
    ALTER_TABLES_V11,
    ALTER_TABLES_V12,
    ALTER_TABLES_V13,
    ALTER_TABLES_V14,
    CREATE_INDICES,
    CREATE_TABLES,
    CREATE_METADATA_FETCHES_V28,
    CREATE_TABLES_V3,
    CREATE_TABLES_V4,
    CREATE_TABLES_V5,
    CREATE_TABLES_V6,
    CREATE_TABLES_V15,
    DELETE_DEFAULT_LISTS_V16,
    DROP_LEGACY_LIST_TYPE_INDEX_V17,
    CREATE_TABLES_V18,
    ALTER_TABLES_V19,
    DROP_ORPHAN_TABLES_V20,
    ADD_ACCOUNT_SCOPE_V21,
    DROP_ORPHAN_TABLES_V22,
    NORMALIZE_GAME_HASH_CASE_V23,
    SCOPE_LIBRARY_PATHS_V24,
    ADD_FLATPAK_CONFIG_V25,
    ADD_ROM_FINGERPRINT_V26,
    PURGE_FOLLOWING_LIST_ENTRIES_V10,
    PURGE_GAMES_WITHOUT_ACHIEVEMENTS_V9,
)

logger = logging.getLogger(__name__)

# Re-export backup helpers under the migrations module for callers that look for
# them here.
create_backup = backup_module.create_backup
backup_database = backup_module.backup_database
create_verified_backup = backup_module.create_verified_backup
verify_backup = backup_module.verify_backup
restore_backup = backup_module.restore_backup
restore_database = backup_module.restore_database
export_database = backup_module.export_database
export_portable = backup_module.export_portable
portable_export = backup_module.portable_export

# Each entry is (version, statements). Add new entries here for future schema
# changes — never edit a migration that has already shipped.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, CREATE_TABLES + CREATE_INDICES),
    (
        2,
        [
            # Unique constraints needed for idempotent upserts in the repository
            # layer (repeated sync/scan must update in place, never duplicate rows).
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_achievements_account_achievement "
            "ON user_achievements(account_id, achievement_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_rom_folders_path ON rom_folders(path)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_installed_roms_file_path "
            "ON installed_roms(file_path)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_badges_account_name "
            "ON badges(account_id, name)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_lists_account_game_type "
            "ON user_lists(account_id, game_id, list_type)",
        ],
    ),
    (3, CREATE_TABLES_V3),
    (4, CREATE_TABLES_V4),
    (5, CREATE_TABLES_V5),
    (6, CREATE_TABLES_V6),
    (7, ALTER_TABLES_V7),
    (8, ALTER_TABLES_V8),
    (9, PURGE_GAMES_WITHOUT_ACHIEVEMENTS_V9),
    (10, PURGE_FOLLOWING_LIST_ENTRIES_V10),
    (11, ALTER_TABLES_V11),
    (12, ALTER_TABLES_V12),
    (13, ALTER_TABLES_V13),
    (14, ALTER_TABLES_V14),
    (15, CREATE_TABLES_V15),
    (16, DELETE_DEFAULT_LISTS_V16),
    (17, DROP_LEGACY_LIST_TYPE_INDEX_V17),
    (18, CREATE_TABLES_V18),
    (19, ALTER_TABLES_V19),
    (20, DROP_ORPHAN_TABLES_V20),
    (21, ADD_ACCOUNT_SCOPE_V21),
    (22, DROP_ORPHAN_TABLES_V22),
    (23, NORMALIZE_GAME_HASH_CASE_V23),
    (24, SCOPE_LIBRARY_PATHS_V24),
    (25, ADD_FLATPAK_CONFIG_V25),
    (26, ADD_ROM_FINGERPRINT_V26),
    (27, ["CREATE TABLE IF NOT EXISTS pending_credential_deletions (username TEXT PRIMARY KEY, created_at TEXT NOT NULL)"]),
    (28, CREATE_METADATA_FETCHES_V28),
]


class UnsupportedDatabaseVersionError(ValueError):
    """Raised when a database schema is newer than this application supports."""


# Alternative names that callers or tests might use.
DatabaseTooNewError = UnsupportedDatabaseVersionError
NewerDatabaseError = UnsupportedDatabaseVersionError
UnsupportedSchemaVersionError = UnsupportedDatabaseVersionError
DatabaseVersionError = UnsupportedDatabaseVersionError


def supported_database_version() -> int:
    if not MIGRATIONS:
        return 0
    return MIGRATIONS[-1][0]


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply pending migrations atomically.

    Each migration runs in its own explicit transaction covering both its schema
    statements and the ``PRAGMA user_version`` bump, so a failure cannot leave
    a half-applied migration behind. Connections whose schema is already newer
    than this build supports are rejected rather than silently downgraded.
    """
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]
    supported_version = supported_database_version()

    if current_version > supported_version:
        raise UnsupportedDatabaseVersionError(
            f"Database schema version {current_version} is newer than this "
            f"application supports ({supported_version})"
        )

    pending = [(version, statements) for version, statements in MIGRATIONS
               if version > current_version]
    if not pending:
        return

    if connection.in_transaction:
        raise ValueError("Migrations require a connection without an active transaction")
    # A failed backup must prevent upgrades of an existing on-disk schema.
    db_path = next((Path(row[2]) for row in connection.execute("PRAGMA database_list")
                    if row[1] == "main" and row[2]), None)
    has_schema = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone() is not None
    if db_path is not None and (current_version > 0 or has_schema):
        backup_path = backup_module.create_backup(connection=connection)
        backup_module.prune_backups(backup_path.parent, keep=backup_module.DEFAULT_RETENTION)
        logger.info("Created pre-migration backup at %s", backup_path)

    previous_isolation = connection.isolation_level
    connection.isolation_level = None
    try:
        for version, statements in pending:
            logger.info("Applying database migration %d", version)
            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in statements:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {version}")
                connection.commit()
            except Exception:
                try:
                    connection.rollback()
                except Exception:  # noqa: BLE001
                    pass
                raise
    finally:
        connection.isolation_level = previous_isolation


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open the database and bring its schema up to date. Caller owns the connection."""
    connection = create_connection(database_path)
    try:
        apply_migrations(connection)
    except BaseException:
        try:
            connection.rollback()
        except Exception:  # noqa: BLE001
            pass
        connection.close()
        raise
    return connection
