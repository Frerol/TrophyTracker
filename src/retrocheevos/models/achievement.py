"""Achievement DTOs — map to `achievements` and `user_achievements` (Database.md 2.5, 2.6)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Achievement:
    id: int  # RetroAchievements achievement ID, externally assigned
    game_id: int
    title: str
    description: str
    points: int
    badge_path: Optional[str] = None


@dataclass
class UserAchievement:
    account_id: int
    achievement_id: int
    hardcore: bool
    unlocked_at: Optional[datetime] = None
    id: Optional[int] = None
