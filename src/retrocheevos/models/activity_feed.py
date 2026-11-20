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
    # When the user was last playing (RA's own "Last seen"). There used to be
    # a `last_achievement_at` beside it, showing the last *unlock* — a
    # different clock that runs behind this one, since a session can go hours
    # without an unlock. Having both on screen invited exactly the confusion
    # it caused; the card shows this one, and the game below is the game this
    # timestamp refers to.
    last_seen_at: Optional[datetime]
    # The game they were last playing, and their progress in it.
    game_title: Optional[str]
    game_console: Optional[str]
    game_icon_path: Optional[Path]
    achievements_unlocked: Optional[int]
    achievements_total: Optional[int]
    playtime_seconds: Optional[int]
    # A summary can still be shown when its optional progress lookup fails.
    progress_unavailable: bool = False


@dataclass
class ActivityFeedResult:
    entries: list[ActivityEntry]
    failed_usernames: list[str]
    following_unavailable: bool = False

    @property
    def partial(self) -> bool:
        return bool(self.failed_usernames or self.following_unavailable)
