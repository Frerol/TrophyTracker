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
    # RetroRatio-weighted total, shown alongside `points` on RA's own site
    # (`API_GetUserProfile.php`'s `TotalTruePoints`, confirmed live).
    true_points: int = 0
    # Path fragment (e.g. `/UserPic/{username}.png`), same base URL as game
    # images — `library/user_pics.py` turns this into a cached local file.
    user_pic_path: Optional[str] = None
    # Which version of the stats formula produced these numbers — see
    # `sync_service.PROFILE_STATS_REVISION`. Lets a changed calculation
    # invalidate the cache, which `last_synced_at` alone cannot.
    stats_revision: int = 0
    last_synced_at: Optional[datetime] = None


@dataclass
class Badge:
    account_id: int
    name: str
    owned: bool
    image_path: Optional[str] = None
    progress: Optional[float] = None
    # True for community-event badges, decided at sync time by
    # `core/mapping.py::map_badge` — separates the Profile page's Event
    # Badges tab from regular badges (Database.md §6.2).
    is_event: bool = False
    id: Optional[int] = None
