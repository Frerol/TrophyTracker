"""Profile read path (UI.md 3.4) — cache-only reads; use sync_service to refresh."""

from typing import Optional

from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.profile_repository import ProfileRepository
from retrocheevos.models.profile import Badge, ProfileStats


def get_profile_stats(account_id: int) -> Optional[ProfileStats]:
    with get_connection() as connection:
        return ProfileRepository(connection).get_stats(account_id)


def get_badges(account_id: int, owned_only: bool = False) -> list[Badge]:
    with get_connection() as connection:
        return ProfileRepository(connection).list_badges(account_id, owned_only)
