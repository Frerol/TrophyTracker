"""Profile DTOs — map to `profile_stats` and `badges` (Database.md 6.1, 6.2)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ProfileStats:
    account_id: int  # primary key, one row per account
    points: int
    hardcore_points: int
    games_beaten: int
    games_mastered: int
    completion_percentage: float
    last_synced_at: Optional[datetime] = None


@dataclass
class Badge:
    account_id: int
    name: str
    owned: bool
    image_path: Optional[str] = None
    progress: Optional[float] = None
    id: Optional[int] = None
