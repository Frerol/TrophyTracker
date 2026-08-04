"""Dashboard read path (UI.md 3.1) — MVP scope: Continue Playing + Recent
Activity + an empty Recommendations placeholder. See `core/dashboard.py` for
what's deliberately left out and why.
"""

from retrocheevos.core.dashboard import get_continue_playing, get_recent_activity, get_recommendations
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.achievement_repository import AchievementRepository
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.models.achievement import UserAchievement
from retrocheevos.models.game import Game


def get_continue_playing_games(account_id: int) -> list[Game]:
    with get_connection() as connection:
        return get_continue_playing(
            account_id,
            game_completion_repository=GameCompletionRepository(connection),
            game_repository=GameRepository(connection),
        )


def get_recent_activity_entries(account_id: int, limit: int = 20) -> list[UserAchievement]:
    with get_connection() as connection:
        return get_recent_activity(
            account_id, achievement_repository=AchievementRepository(connection), limit=limit
        )


def get_recommended_games(account_id: int) -> list[Game]:
    return get_recommendations(account_id)
