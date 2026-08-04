"""Cache staleness rules (Database.md §7). `api/` never decides when to
refresh on its own (API.md §5) — this is the Core decision it defers to.
"""

from datetime import datetime, timedelta
from typing import Optional

from retrocheevos.models.game import Game

GAME_METADATA_STALE_AFTER = timedelta(days=7)


def is_game_metadata_stale(game: Game, now: Optional[datetime] = None) -> bool:
    """True if `game` was never synced, or its last sync is older than the staleness window."""
    if game.last_synced_at is None:
        return True
    current_time = now or datetime.now()
    return current_time - game.last_synced_at > GAME_METADATA_STALE_AFTER
