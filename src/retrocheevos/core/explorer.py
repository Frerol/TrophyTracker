"""Explorer search/filter rules (UI.md 3.2, Database.md §4.1).

`GameRepository.search()` only handles DB-level predicates (text, console,
game type) — it always excludes games without an achievement set,
unconditionally, since those are never synced/stored at all. Everything that
depends on another table — list membership, installed status, mastery — is a
Core decision layered on top here, combining multiple repositories for one
use case.
"""

from dataclasses import dataclass
from typing import Optional

from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.utils.enums import GameType, ListType

SECONDS_PER_MINUTE = 60


@dataclass
class ExplorerFilters:
    search_text: Optional[str] = None
    console_ids: Optional[list[int]] = None
    game_types: Optional[list[GameType]] = None
    # "Show me something I can finish in under N minutes". Games with no
    # known median time are excluded when this is set — an unknown duration
    # can't be claimed to fit within a limit. Only populated per-console by
    # `sync_service.sync_median_times_for_console`; the bulk catalog sync
    # doesn't carry this field (`API_GetGameList.php` doesn't return it).
    max_median_time_minutes: Optional[int] = None
    installed_only: bool = False
    # Narrow results to games in any of these lists, by `list_id`. Was
    # `list_types_any_of` and keyed on the `ListType` enum, which only worked
    # while the set of lists was fixed — with user-created lists (Bloco 12)
    # a list has no enum member to name it by.
    #
    # The `show_completed`/`show_abandoned` reveal toggles that used to live
    # here are gone with the predefined lists they read (migration v16).
    # Nothing is lost from search: already-finished games are still excluded
    # unconditionally in `search_games` below, from `game_completion` — which
    # is RA's own record, not a list the user had to maintain by hand.
    list_ids_any_of: Optional[list[int]] = None


def search_games(
    account_id: int,
    filters: ExplorerFilters,
    *,
    game_repository: GameRepository,
    list_repository: ListRepository,
    library_repository: LibraryRepository,
    game_completion_repository: GameCompletionRepository,
) -> list[Game]:
    """Cache-only Explorer search. Never triggers a network call (UI.md 3.2, API.md §4)."""
    games = game_repository.search(
        text=filters.search_text,
        console_ids=filters.console_ids,
        game_types=filters.game_types,
    )

    # Always excluded, unlike show_completed/show_abandoned below — no
    # opt-in reveal filter. Blocking is only reversible from the Blocked list
    # on the Lists page, via its per-game "−" button (Database.md 4.1).
    blocked_ids = list_repository.get_game_ids_by_slug(account_id, ListType.BLOCKED)
    games = [g for g in games if g.id not in blocked_ids]

    if filters.max_median_time_minutes is not None:
        # The `is not None` guard isn't optional — the column is nullable and
        # `None <= int` is a TypeError in Python 3.
        max_seconds = filters.max_median_time_minutes * SECONDS_PER_MINUTE
        games = [
            g
            for g in games
            if g.median_time_to_beat_hardcore_seconds is not None
            and g.median_time_to_beat_hardcore_seconds <= max_seconds
        ]

    if filters.installed_only:
        installed_ids = library_repository.get_installed_game_ids()
        games = [g for g in games if g.id in installed_ids]

    if filters.list_ids_any_of:
        matching_ids: set[int] = set()
        for list_id in filters.list_ids_any_of:
            matching_ids |= list_repository.get_game_ids_in_list(account_id, list_id)
        games = [g for g in games if g.id in matching_ids]

    # Unconditional — no reveal toggle (per user decision): a game already
    # finished never belongs in
    # "what should I play next" search. Both sets come from `game_completion`
    # rather than the `achievements`/`user_achievements` tables an earlier
    # version consulted — nothing in the app populates those, so that check
    # matched nothing and mastered games leaked into results.
    finished_ids = game_completion_repository.get_finished_game_ids(account_id)
    finished_ids |= game_completion_repository.get_fully_completed_game_ids(account_id)
    games = [g for g in games if g.id not in finished_ids]

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
    game_completion_repository: GameCompletionRepository,
) -> list[GameWithCompletion]:
    games = search_games(
        account_id,
        filters,
        game_repository=game_repository,
        list_repository=list_repository,
        library_repository=library_repository,
        game_completion_repository=game_completion_repository,
    )
    completion_by_game_id = game_completion_repository.get_all_for_account(account_id)
    return [
        GameWithCompletion(game=game, percent_complete=completion_by_game_id.get(game.id))
        for game in games
    ]


def total_game_count(*, game_repository: GameRepository) -> int:
    """All synced games, unfiltered — the "Y" in Explorer's "X of Y games" counter."""
    return game_repository.count_all()
