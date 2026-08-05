"""Recent Activity feed domain model (UI.md — Home screen, RA "Following"-
page-style redesign). See `services/activity_feed_service.py` for how this
is built — a live read against the API, never persisted to the local DB
(Architecture.md: this data is ephemeral, not "library" data).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ActivityEntry:
    username: str
    is_self: bool
    avatar_path: Optional[Path]
    status_text: str
    last_achievement_at: Optional[datetime]
    game_title: Optional[str]
    game_console: Optional[str]
    game_icon_path: Optional[Path]
    achievements_unlocked: Optional[int]
    achievements_total: Optional[int]
    playtime_seconds: Optional[int]
