"""List membership rules (Database.md 4.1) — `services/lists_service.py`'s
Core counterpart, matching `core/explorer.py`/`core/dashboard.py`.
"""

from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.utils.enums import ListType


def get_games_in_list(
    account_id: int,
    list_type: ListType,
    *,
    list_repository: ListRepository,
    game_repository: GameRepository,
) -> list[Game]:
    """Full `Game` rows for one list. A blocked game is excluded from every
    *other* list's view too — being blocked hides it everywhere except
    Settings' dedicated Blocked Games management list (Database.md 4.1).
    """
    game_ids = list_repository.get_game_ids_in_list(account_id, list_type)
    if list_type != ListType.BLOCKED:
        blocked_ids = list_repository.get_game_ids_in_list(account_id, ListType.BLOCKED)
        game_ids = game_ids - blocked_ids

    games = (game_repository.get_by_id(game_id) for game_id in game_ids)
    return [game for game in games if game is not None]
