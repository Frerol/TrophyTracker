"""Game DTOs — map to `games` and `game_hashes` (Database.md 2.3, 2.4)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.utils.enums import GameType


@dataclass
class Game:
    id: int  # RetroAchievements game ID, externally assigned
    title: str
    console_id: int
    has_achievements: bool
    image_path: Optional[str] = None
    genre: Optional[str] = None
    game_type: Optional[GameType] = None
    median_time_to_beat_hardcore_seconds: Optional[int] = None
    times_used_in_hardcore_beat_median: Optional[int] = None
    retroachievements_url: Optional[str] = None
    last_synced_at: Optional[datetime] = None


@dataclass
class GameHash:
    game_id: int
    hash: str
    id: Optional[int] = None
