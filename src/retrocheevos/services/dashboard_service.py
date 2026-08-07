"""Dashboard read path (UI.md 3.1) — MVP scope: Continue Playing + Recent
Activity + an empty Recommendations placeholder. See `core/dashboard.py` for
what's deliberately left out and why.
"""

from retrocheevos.core.dashboard import ContinuePlayingEntry, get_continue_playing, get_recommendations
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom


def get_continue_playing_games(account_id: int) -> list[ContinuePlayingEntry]:
    with get_connection() as connection:
        return get_continue_playing(
            account_id,
            game_completion_repository=GameCompletionRepository(connection),
            game_repository=GameRepository(connection),
            list_repository=ListRepository(connection),
            library_repository=LibraryRepository(connection, account_id),
        )


def get_unmatched_continue_playing_roms(account_id: int) -> list[InstalledRom]:
    """ROMs hashing (and no manual match yet) resolved to no game — shown as
    a fallback alongside `get_continue_playing_games` (`gui/pages/home_page.py`)
    rather than being hidden entirely.

    Account-scoped since schema v21. It previously wasn't — and couldn't be,
    because `installed_roms` had no owner — so two people sharing an install
    saw each other's unmatched ROMs here.
    """
    with get_connection() as connection:
        return LibraryRepository(connection, account_id).get_unmatched_installed_roms()


def get_recommended_games(account_id: int) -> list[Game]:
    return get_recommendations(account_id)
