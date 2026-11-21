"""Dashboard rules (UI.md 3.1) — MVP scope only.

Reduced by design: Recommendations is a v1.1 feature
(original release plan, docs/archive/RoadmapHistory.md), left as an empty placeholder. Events and
"Recently added achievements" need data this project doesn't have yet
(no achievement-added timestamp in the schema, no Events endpoint modeled)
and have been moved to v1.1 in that plan rather than faked here.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.utils.enums import ListType

MAX_CONTINUE_PLAYING_PERCENT = 100.0


@dataclass
class ContinuePlayingEntry:
    """A Game plus when it was last launched and how far along it is, for
    Home's Continue Playing grid — `installed_roms.last_played_at` is keyed
    by ROM, not game, so this carries the resolved value (max across every
    local copy) alongside the `Game` itself rather than the GUI needing a
    second lookup. `percent_complete` is None when the account has no
    tracked progress for this game at all.
    """

    game: Game
    last_played_at: Optional[datetime]
    percent_complete: Optional[float]
    # RA's combined unlocked/total count (D8); None when only a percentage,
    # or nothing, is known.
    achievements_unlocked: Optional[int] = None
    achievements_total: Optional[int] = None


def get_continue_playing(
    account_id: int,
    *,
    game_completion_repository: GameCompletionRepository,
    game_repository: GameRepository,
    list_repository: ListRepository,
    library_repository: LibraryRepository,
) -> list[ContinuePlayingEntry]:
    """Every installed game that isn't finished or blocked.

    Starts from `installed_roms` (what's actually playable right now) rather
    than from `game_completion` (what has achievement progress): most of a
    typical library has no progress row at all, so keying off progress left
    the section nearly empty and hid games the user had just installed or
    manually matched. Progress is attached when it exists and drives
    ordering in the GUI, but its absence no longer excludes a game.

    Only blocked games are excluded. Finished ones used to be dropped too,
    on the reasoning that a completed game isn't something to "continue" —
    but that made installed games vanish from the one place that lists what
    you can actually play right now, which is more surprising than useful.
    They're kept and sorted last instead (`gui/pages/home_page.py`).
    """
    completion_by_game_id = game_completion_repository.get_all_for_account(account_id)
    counts_by_game_id = game_completion_repository.get_achievement_counts_for_account(account_id)
    blocked_ids = list_repository.get_game_ids_by_slug(account_id, ListType.BLOCKED)
    installed_ids = library_repository.get_installed_game_ids()
    last_played_by_game_id = library_repository.get_last_played_by_game_id()

    entries: list[ContinuePlayingEntry] = []
    for game_id in installed_ids:
        if game_id in blocked_ids:
            continue
        percent = completion_by_game_id.get(game_id)
        game = game_repository.get_by_id(game_id)
        # `get_by_id` is intentionally left unfiltered (ROM-hash matching in
        # `services/library_service.py` needs it to still resolve a game even
        # if it has no achievement set) — guard against it resurfacing one.
        if game is None or not game.has_achievements:
            continue
        unlocked, total = counts_by_game_id.get(game_id, (None, None))
        entries.append(
            ContinuePlayingEntry(
                game=game,
                last_played_at=last_played_by_game_id.get(game_id),
                percent_complete=percent,
                achievements_unlocked=unlocked,
                achievements_total=total,
            )
        )
    return entries
