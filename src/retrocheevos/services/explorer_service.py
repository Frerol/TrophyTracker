"""Explorer read path (UI.md 3.2) — cache-only, never triggers a sync (API.md §4)."""

from retrocheevos.core.explorer import (
    ExplorerFilters,
    GameWithCompletion,
    search_games_with_completion,
    total_game_count,
)
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.achievement_repository import AchievementRepository
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.list_repository import ListRepository


def get_games(account_id: int, filters: ExplorerFilters) -> list[GameWithCompletion]:
    with get_connection() as connection:
        return search_games_with_completion(
            account_id,
            filters,
            game_repository=GameRepository(connection),
            list_repository=ListRepository(connection),
            library_repository=LibraryRepository(connection),
            achievement_repository=AchievementRepository(connection),
            game_completion_repository=GameCompletionRepository(connection),
        )


def get_total_game_count() -> int:
    with get_connection() as connection:
        return total_game_count(game_repository=GameRepository(connection))
