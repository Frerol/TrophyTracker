"""Dashboard rules (UI.md 3.1) — MVP scope only.

Reduced by design: Recommendations is a v1.1 feature
(DevelopmentRoadmap.md), left as an empty placeholder. Events and
"Recently added achievements" need data this project doesn't have yet
(no achievement-added timestamp in the schema, no Events endpoint modeled)
and have been moved to v1.1 in DevelopmentRoadmap.md rather than faked here.
"""

from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.utils.enums import ListType

MIN_CONTINUE_PLAYING_PERCENT = 0.0
MAX_CONTINUE_PLAYING_PERCENT = 100.0


def get_continue_playing(
    account_id: int,
    *,
    game_completion_repository: GameCompletionRepository,
    game_repository: GameRepository,
    list_repository: ListRepository,
) -> list[Game]:
    """Games with partial progress: started (>0%) but not finished (<100%)."""
    completion_by_game_id = game_completion_repository.get_all_for_account(account_id)
    blocked_ids = list_repository.get_game_ids_in_list(account_id, ListType.BLOCKED)
    game_ids = [
        game_id
        for game_id, percent in completion_by_game_id.items()
        if MIN_CONTINUE_PLAYING_PERCENT < percent < MAX_CONTINUE_PLAYING_PERCENT
        and game_id not in blocked_ids
    ]
    games = (game_repository.get_by_id(game_id) for game_id in game_ids)
    return [game for game in games if game is not None]


def get_recommendations(account_id: int) -> list[Game]:
    """Placeholder — the real recommendation engine is v1.1 (DevelopmentRoadmap.md)."""
    return []
