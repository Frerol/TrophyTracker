"""Profile read path (UI.md 3.4) — cache-only reads; use sync_service to refresh."""

from typing import Optional

from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.profile_repository import ProfileRepository
from retrocheevos.models.profile import Badge, ProfileStats


def get_profile_stats(account_id: int) -> Optional[ProfileStats]:
    with get_connection() as connection:
        return ProfileRepository(connection).get_stats(account_id)


def list_badges(account_id: int) -> list[Badge]:
    """Synced badges and event awards for the Awards view (D7)."""
    with get_connection() as connection:
        return ProfileRepository(connection).list_badges(account_id)
