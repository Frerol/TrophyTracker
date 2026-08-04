"""SQLite connection management (Architecture.md — Database layer)."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "retrocheevos.db"

logger = logging.getLogger(__name__)


def create_connection(database_path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with the app's standard PRAGMAs applied."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    logger.debug("Opened SQLite connection at %s", database_path)
    return connection


@contextmanager
def get_connection(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> Iterator[sqlite3.Connection]:
    """Yield a connection for one unit of work; commits on success, rolls back on error."""
    connection = create_connection(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        logger.exception("Database operation failed, rolled back")
        raise
    finally:
        connection.close()
