"""Account session management (UI.md 3.7 Settings — "switch account").

Every function opens its own short-lived connection (`get_connection`)
rather than sharing one across calls — SQLite connections aren't safe to
share across threads, and sync operations run on background threads
(CodingStandards' threading model), so each call must be self-contained.
"""

from typing import Optional

from retrocheevos.api.client import RetroAchievementsClient
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.account_repository import AccountRepository
from retrocheevos.models.account import Account


def add_account(username: str, api_key: str, activate: bool = True) -> Account:
    with get_connection() as connection:
        repository = AccountRepository(connection)
        account = repository.add(Account(username=username, api_key=api_key, is_active=activate))
        if activate:
            repository.set_active(account.id)
        return account


def remove_account(account_id: int) -> None:
    with get_connection() as connection:
        AccountRepository(connection).remove(account_id)


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
