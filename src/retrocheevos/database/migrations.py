"""Versioned schema migrations, tracked via SQLite's `PRAGMA user_version`."""

import logging
import sqlite3
from pathlib import Path

from retrocheevos.database.connection import DEFAULT_DATABASE_PATH, create_connection
from retrocheevos.database.schema import (
    ALTER_TABLES_V7,
    CREATE_INDICES,
    CREATE_TABLES,
    CREATE_TABLES_V3,
    CREATE_TABLES_V4,
    CREATE_TABLES_V5,
    CREATE_TABLES_V6,
)

logger = logging.getLogger(__name__)

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
]


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply any migration whose version is newer than the database's current version."""
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]

    for version, statements in MIGRATIONS:
        if version <= current_version:
            continue
        logger.info("Applying database migration %d", version)
        for statement in statements:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {version}")

    connection.commit()


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open the database and bring its schema up to date. Caller owns the connection."""
    connection = create_connection(database_path)
    apply_migrations(connection)
    return connection
