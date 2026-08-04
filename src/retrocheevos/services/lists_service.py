"""List management (UI.md 3.6, Database.md §4.1)."""

from datetime import datetime

from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.models.list_entry import ListEntry
from retrocheevos.utils.enums import ListType


def add_to_list(account_id: int, game_id: int, list_type: ListType) -> None:
    with get_connection() as connection:
        ListRepository(connection).add_to_list(
            ListEntry(
                account_id=account_id,
                game_id=game_id,
                list_type=list_type,
                added_at=datetime.now(),
            )
        )


def remove_from_list(account_id: int, game_id: int, list_type: ListType) -> None:
    with get_connection() as connection:
        ListRepository(connection).remove_from_list(account_id, game_id, list_type)


def get_list_types_for_game(account_id: int, game_id: int) -> list[ListType]:
    with get_connection() as connection:
        return ListRepository(connection).get_list_types_for_game(account_id, game_id)


def get_games_in_list(account_id: int, list_type: ListType) -> list[Game]:
    """Full `Game` rows for a list screen (UI.md 3.6 — reuses the Game Card)."""
    with get_connection() as connection:
        list_repository = ListRepository(connection)
        game_repository = GameRepository(connection)
        game_ids = list_repository.get_game_ids_in_list(account_id, list_type)
        return [
            game
            for game_id in game_ids
            if (game := game_repository.get_by_id(game_id)) is not None
        ]
