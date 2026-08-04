"""LeaderboardEntry DTO — maps to the `leaderboard_cache` table (Database.md 6.3)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.utils.enums import LeaderboardScope


@dataclass
class LeaderboardEntry:
    scope: LeaderboardScope
    account_id: int
    payload_json: str
    last_synced_at: Optional[datetime] = None
    id: Optional[int] = None
