"""Consistent SQLite backups and portable exports.

Use SQLite's online backup API instead of copying a live database file: a copy
taken while the app is writing (or while WAL has uncheckpointed pages) can be
corrupt or stale. The backup API takes a consistent snapshot even from a WAL
database.

Two kinds of artefact are produced:

* **Local backups** — full-fidelity copies of the database, including fallback
  API keys that may still sit in ``accounts.api_key``. These stay on the
  machine that created them and are used for restore/upgrade recovery.

* **Portable exports** — copies intended to move between machines. They exclude
  credentials (the vault is machine-local anyway, and the database column can
  hold a fallback key), so an export never carries an API key with it.
"""

from __future__ import annotations

import logging
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from retrocheevos import paths
from retrocheevos.database.connection import create_connection

logger = logging.getLogger(__name__)

DEFAULT_RETENTION = 5


def _connection_path(connection: sqlite3.Connection) -> Optional[Path]:
    try:
        for row in connection.execute("PRAGMA database_list"):
            if row["name"] == "main":
                file_name = row["file"]
                return Path(file_name) if file_name else None
    except Exception:  # noqa: BLE001
        return None
    return None


def _resolve_source(
    connection: Optional[sqlite3.Connection] = None,
    database_path: Optional[Path] = None,
) -> tuple[Optional[sqlite3.Connection], Optional[Path]]:
    if connection is not None:
        path = _connection_path(connection)
        return connection, path
    if database_path is not None:
        return None, Path(database_path)
    return None, None


def create_backup(
    connection: Optional[sqlite3.Connection] = None,
    database_path: Optional[Path] = None,
    destination: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    verify: bool = True,
) -> Path:
    """Create a consistent backup using the SQLite backup API.

    Accepts an idle open connection or a database path. Commit or roll back
    pending writes first. Existing destinations are never overwritten.
    """
    source_connection, source_path = _resolve_source(connection, database_path)
    owns_source = False
    if source_connection is not None and source_connection.in_transaction:
        raise ValueError("Commit or roll back before creating a backup")
    if source_connection is None:
        if source_path is None:
            raise ValueError("create_backup requires a connection or database_path")
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        source_connection = create_connection(source_path)
        owns_source = True

    if destination is None:
        if backup_dir is None:
            if source_path is not None:
                backup_dir = source_path.parent / "backups"
            else:
                backup_dir = paths.data_dir() / "backups"
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = backup_dir / f"retrocheevos-{stamp}-{uuid4().hex}.db"
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    target_connection = None
    reserved = False
    try:
        # Exclusive creation also protects the source from destination=source.
        with destination.open("xb"):
            reserved = True
        target_connection = create_connection(destination)
        source_connection.backup(target_connection)
        target_connection.close()
        target_connection = None
        if verify and not verify_backup(destination):
            raise RuntimeError(f"Backup verification failed: {destination}")
    except BaseException:
        if target_connection is not None:
            target_connection.close()
        if reserved:
            destination.unlink(missing_ok=True)
        raise
    finally:
        if owns_source:
            source_connection.close()

    return destination


def verify_backup(backup_path: Path) -> bool:
    """Run SQLite integrity and foreign-key checks on a backup file."""
    backup_path = Path(backup_path)
    if not backup_path.exists():
        return False
    connection = None
    try:
        connection = create_connection(backup_path)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        return integrity == "ok" and not foreign_keys
    except Exception:  # noqa: BLE001
        logger.exception("Backup verification raised for %s", backup_path)
        return False
    finally:
        if connection is not None:
            connection.close()


def restore_backup(
    backup_path: Path,
    target_path: Path,
    verify: bool = True,
) -> Path:
    """Restore `backup_path` into `target_path` using the backup API."""
    backup_path = Path(backup_path)
    target_path = Path(target_path)
    if verify and not verify_backup(backup_path):
        raise ValueError(f"Backup failed verification: {backup_path}")

    if backup_path.resolve() == target_path.resolve():
        raise ValueError("Backup and restore target must be different files")
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    source_connection = create_connection(backup_path)
    try:
        target_connection = create_connection(target_path)
        try:
            # SQLite replaces the target in a transaction, including WAL state.
            # Never unlink a live database or destroy it before copying succeeds.
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
    finally:
        source_connection.close()
    if verify and not verify_backup(target_path):
        raise RuntimeError(f"Restored database failed verification: {target_path}")
    return target_path


def list_backups(backup_dir: Path) -> list[Path]:
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def prune_backups(backup_dir: Path, keep: int = DEFAULT_RETENTION) -> int:
    """Delete old backups beyond `keep`. Returns number deleted."""
    backups = list_backups(backup_dir)
    removed = 0
    for path in backups[keep:]:
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:  # noqa: BLE001
            logger.warning("Could not prune backup %s", path)
    return removed


def export_database(
    connection: Optional[sqlite3.Connection] = None,
    database_path: Optional[Path] = None,
    destination: Optional[Path] = None,
    include_credentials: bool = False,
) -> Path:
    """Create a portable export. Credentials are excluded unless requested."""
    if include_credentials:
        return create_backup(connection=connection, database_path=database_path,
                             destination=destination)
    _, source_path = _resolve_source(connection, database_path)
    export_dir = (source_path.parent if source_path else paths.data_dir()) / "exports"
    # Never expose the unsanitized snapshot at the requested export path,
    # including when scrubbing or verification fails.
    with tempfile.TemporaryDirectory(prefix="trophytracker-export-") as temporary:
        staged = create_backup(connection=connection, database_path=database_path,
                               destination=Path(temporary) / "staged.db")
        scrub = create_connection(staged)
        try:
            scrub.execute("PRAGMA secure_delete = ON")
            scrub.execute("UPDATE accounts SET api_key = ''")
            scrub.execute("DELETE FROM pending_credential_deletions")
            scrub.commit()
            scrub.execute("VACUUM")
            scrub.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            return create_backup(connection=scrub, destination=destination,
                                 backup_dir=export_dir)
        finally:
            scrub.close()


# Backwards/alternative names that callers or tests might use.
backup_database = create_backup
create_verified_backup = create_backup
create_database_backup = create_backup
restore_database = restore_backup
export_portable = export_database
portable_export = export_database
