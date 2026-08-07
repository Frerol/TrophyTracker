"""Community events read path — cache-only, like `explorer_service`.

RetroAchievements models each event as a game on its own console, so events
come out of the same `games` table as everything else; the catalog queries
just exclude that console deliberately
(`database/repositories/game_repository.py`), and this is the way in.
Progress counts are filled by `sync_service.sync_event_progress`.
"""

from dataclasses import dataclass
from typing import Optional

from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.models.game import Game


@dataclass
class EventWithProgress:
    """An event plus how far this account has got in it. Counts are None
    until a sync has fetched them (they come from a per-event API call, not
    from the catalog sync that stores the event itself).
    """

    game: Game
    achievements_unlocked: Optional[int]
    achievements_total: Optional[int]

    @property
    def is_started(self) -> bool:
        return bool(self.achievements_unlocked)


def list_events_with_progress(account_id: int) -> list[EventWithProgress]:
    """Events ordered the way they're most useful to look at: ones already
    started first (and among those, closest to completion first), then the
    rest alphabetically.
    """
    with get_connection() as connection:
        events = GameRepository(connection).list_events()
        counts = GameCompletionRepository(connection).get_achievement_counts_for_account(
            account_id
        )

    entries = []
    for event in events:
        unlocked, total = counts.get(event.id, (None, None))
        entries.append(
            EventWithProgress(
                game=event, achievements_unlocked=unlocked, achievements_total=total
            )
        )

    def sort_key(entry: EventWithProgress) -> tuple:
        completion = (
            entry.achievements_unlocked / entry.achievements_total
            if entry.is_started and entry.achievements_total
            else 0.0
        )
        return (0 if entry.is_started else 1, -completion, entry.game.title.lower())

    entries.sort(key=sort_key)
    return entries
