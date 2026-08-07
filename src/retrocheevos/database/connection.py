"""SQLite connection management (Architecture.md — Database layer)."""

import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    """Where this install keeps its data.

    Frozen (PyInstaller) builds get a **per-user OS data directory**;
    running from source keeps using the repo's `database/` folder so
    development is unchanged.

    Both halves matter for shipping an .exe:

    - `PROJECT_ROOT` is derived from `__file__`, which inside a one-file
      build points at the temporary extraction directory. The database would
      be created there and vanish with the process, or worse, be written next
      to the executable in Program Files where a normal user can't write.
    - It also keeps one person's database out of another's install. The data
      belongs to whoever is logged into the machine, not to the copy of the
      program — which is what makes "give the .exe to a friend" safe: there
      is nothing of yours inside it, and his data lands under his own user
      profile.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / f".{APP_DIR_NAME.lower()}"
    # From source: the repo root, so `database/` and `logs/` stay exactly
    # where they have always been and nothing about development changes.
    return PROJECT_ROOT


APP_DIR_NAME = "Retrocheevos"
DEFAULT_DATABASE_PATH = default_data_dir() / "database" / "retrocheevos.db"

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
