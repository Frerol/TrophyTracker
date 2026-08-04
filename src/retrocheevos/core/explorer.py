"""Explorer search/filter rules (UI.md 3.2, Database.md §4.1).

`GameRepository.search()` only handles DB-level predicates (text, console,
game type, has_achievements). Everything that depends on another table —
list membership, installed status, mastery — is a Core decision layered on
top here, combining multiple repositories for one use case.
"""

from dataclasses import dataclass
from typing import Optional

from retrocheevos.database.repositories.achievement_repository import AchievementRepository
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.utils.enums import GameType, ListType


@dataclass
class ExplorerFilters:
    search_text: Optional[str] = None
    console_ids: Optional[list[int]] = None
    game_types: Optional[list[GameType]] = None
    has_achievements: Optional[bool] = None
    require_known_median_time: bool = False
    installed_only: bool = False
    list_types_any_of: Optional[list[ListType]] = None
    # Database.md 4.1 / UI.md 3.2.1: hidden by default, opt-in via filters.
    show_completed: bool = False
    show_abandoned: bool = False
    show_mastered: bool = False


def search_games(
    account_id: int,
    filters: ExplorerFilters,
    *,
    game_repository: GameRepository,
    list_repository: ListRepository,
    library_repository: LibraryRepository,
    achievement_repository: AchievementRepository,
) -> list[Game]:
    """Cache-only Explorer search. Never triggers a network call (UI.md 3.2, API.md §4)."""
    games = game_repository.search(
        text=filters.search_text,
        console_ids=filters.console_ids,
        game_types=filters.game_types,
        has_achievements=filters.has_achievements,
    )

    if filters.require_known_median_time:
        games = [g for g in games if g.median_time_to_beat_hardcore_seconds is not None]

    if filters.installed_only:
        installed_ids = library_repository.get_installed_game_ids()
        games = [g for g in games if g.id in installed_ids]

    if filters.list_types_any_of:
        matching_ids: set[int] = set()
        for list_type in filters.list_types_any_of:
            matching_ids |= list_repository.get_game_ids_in_list(account_id, list_type)
        games = [g for g in games if g.id in matching_ids]

    if not filters.show_completed:
        completed_ids = list_repository.get_game_ids_in_list(account_id, ListType.COMPLETED)
        games = [g for g in games if g.id not in completed_ids]

    if not filters.show_abandoned:
        abandoned_ids = list_repository.get_game_ids_in_list(account_id, ListType.ABANDONED)
        games = [g for g in games if g.id not in abandoned_ids]

    if not filters.show_mastered:
        mastered_ids = achievement_repository.get_mastered_game_ids(account_id)
        games = [g for g in games if g.id not in mastered_ids]

    return games


@dataclass
class GameWithCompletion:
    """A Game plus this account's completion %, for the Explorer Game Card's progress bar."""

    game: Game
    percent_complete: Optional[float]  # None: account has no tracked progress for this game


def search_games_with_completion(
    account_id: int,
    filters: ExplorerFilters,
    *,
    game_repository: GameRepository,
    list_repository: ListRepository,
    library_repository: LibraryRepository,
    achievement_repository: AchievementRepository,
    game_completion_repository: GameCompletionRepository,
) -> list[GameWithCompletion]:
    games = search_games(
        account_id,
        filters,
        game_repository=game_repository,
        list_repository=list_repository,
        library_repository=library_repository,
        achievement_repository=achievement_repository,
    )
    completion_by_game_id = game_completion_repository.get_all_for_account(account_id)
    return [
        GameWithCompletion(game=game, percent_complete=completion_by_game_id.get(game.id))
        for game in games
    ]
