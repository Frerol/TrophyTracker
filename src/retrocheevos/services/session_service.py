"""Account session management (UI.md 3.7 Settings — "switch account").

Every function opens its own short-lived connection (`get_connection`)
rather than sharing one across calls — SQLite connections aren't safe to
share across threads, and sync operations run on background threads
(CodingStandards' threading model), so each call must be self-contained.
"""

import logging
from typing import Optional

from retrocheevos.api.client import RetroAchievementsClient
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.account_repository import AccountRepository
from retrocheevos.library.local_covers import cached_local_cover_path
from retrocheevos.models.account import Account

logger = logging.getLogger(__name__)


def add_account(username: str, api_key: str, activate: bool = True) -> Account:
    with get_connection() as connection:
        repository = AccountRepository(connection)
        account = repository.add(Account(username=username, api_key=api_key, is_active=activate))
        if activate:
            repository.set_active(account.id)
        return account


def count_account_data(account_id: int) -> dict[str, int]:
    """How much data `remove_account` would destroy, per table.

    Exists so the confirmation dialog can say "384 completions, 74 ROMs"
    instead of "are you sure?" — the numbers are what tell someone whether
    they are about to lose the account they meant or the one they didn't.

    Only non-empty counts come back, keyed by a human label.
    """
    labels = {
        "game_completion": "game completions",
        "installed_roms": "installed ROMs",
        "rom_folders": "ROM folders",
        "user_lists": "list entries",
        "user_list_definitions": "lists",
        "badges": "badges",
        "user_achievements": "unlocked achievements",
        "notifications": "notifications",
    }
    counts: dict[str, int] = {}
    with get_connection() as connection:
        for table, label in labels.items():
            total = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE account_id = ?", (account_id,)
            ).fetchone()[0]
            if total:
                counts[label] = total
    return counts


def remove_account(account_id: int) -> None:
    """Delete an account, its database rows, and the cover images it owned.

    The cover files are collected *before* the delete, because they are keyed
    by `installed_roms.id` and that row is about to be gone.

    They are not a correctness risk — `installed_roms.id` is `AUTOINCREMENT`,
    so SQLite never reuses an id and a future ROM cannot inherit a deleted
    account's artwork. They are hand-picked images belonging to someone who
    asked to be removed, so they go with the rest of it.

    File deletion happens after the transaction commits and cannot fail the
    removal: a locked or already-missing file must not resurrect an account
    whose rows are gone.
    """
    with get_connection() as connection:
        cover_paths = [
            cached_local_cover_path(row["id"])
            for row in connection.execute(
                "SELECT id FROM installed_roms WHERE account_id = ?", (account_id,)
            )
        ]
        AccountRepository(connection).remove(account_id)

    for path in cover_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:  # noqa: PERF203 — one bad file mustn't stop the rest
            logger.info("Could not delete cover %s: %s", path, error)


def list_accounts() -> list[Account]:
    with get_connection() as connection:
        return AccountRepository(connection).list_all()


def get_active_account() -> Optional[Account]:
    with get_connection() as connection:
        return AccountRepository(connection).get_active()


def switch_account(account_id: int) -> None:
    with get_connection() as connection:
        AccountRepository(connection).set_active(account_id)


def logout() -> None:
    """Clears the active account without removing it — still listed in
    Settings, reachable again via "Switch to Selected"."""
    with get_connection() as connection:
        AccountRepository(connection).deactivate_all()


def build_api_client(account: Account) -> RetroAchievementsClient:
    return RetroAchievementsClient(username=account.username, api_key=account.api_key)
