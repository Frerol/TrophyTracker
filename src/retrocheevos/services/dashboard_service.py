"""Dashboard read path (UI.md 3.1) — MVP scope: Continue Playing + Recent
Activity + an empty Recommendations placeholder. See `core/dashboard.py` for
what's deliberately left out and why.
"""

from retrocheevos.core.dashboard import get_continue_playing, get_recommendations
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game


def get_continue_playing_games(account_id: int) -> list[Game]:
    with get_connection() as connection:
        return get_continue_playing(
            account_id,
            game_completion_repository=GameCompletionRepository(connection),
            game_repository=GameRepository(connection),
            list_repository=ListRepository(connection),
        )


def get_recommended_games(account_id: int) -> list[Game]:
    return get_recommendations(account_id)
