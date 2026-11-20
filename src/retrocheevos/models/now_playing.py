"""Current game and achievement progress for the Home panel."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class LiveAchievement:
    id: int
    title: str
    description: str
    points: int
    unlocked_at: Optional[datetime] = None
    hardcore: bool = False


@dataclass
class NowPlayingSnapshot:
    account_id: int
    game_id: Optional[int]
    title: str
    presence: str = ''
    active: bool = False
    source: str = 'retroachievements'
    achievements: list[LiveAchievement] = field(default_factory=list)
    checked_at: Optional[datetime] = None
    notice: str = ''
