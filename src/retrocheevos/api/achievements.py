"""Per-account achievement unlock progress (API.md §3 — 'per-account unlock state')."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.api.client import RetroAchievementsClient
from retrocheevos.api.serialization import parse_ra_datetime


@dataclass
class RawUnlockedAchievement:
    achievement_id: int
    unlocked_at: Optional[datetime]
    hardcore: bool


@dataclass
class RawLiveAchievement:
    id: int
    title: str
    description: str
    points: int
    unlocked_at: Optional[datetime]
    hardcore: bool


@dataclass
class RawLiveGameProgress:
    game_id: int
    title: str
    achievements: list[RawLiveAchievement]


class AchievementProgressClient:
    def __init__(self, client: RetroAchievementsClient) -> None:
        self._client = client

    def get_live_game_progress(self, username: str, game_id: int) -> RawLiveGameProgress:
        payload = self._client.get(
            "API_GetGameInfoAndUserProgress.php", {"u": username, "g": game_id}
        )
        achievements = []
        for key, data in (payload.get("Achievements") or {}).items():
            # Core achievements only; unofficial entries are not part of the set.
            if data.get("Flags", 3) not in (3, "3"):
                continue
            hardcore_date = data.get("DateEarnedHardcore")
            achievements.append(RawLiveAchievement(
                id=int(data.get("ID", key)), title=data.get("Title", ""),
                description=data.get("Description", ""), points=int(data.get("Points") or 0),
                unlocked_at=parse_ra_datetime(hardcore_date or data.get("DateEarned")),
                hardcore=bool(hardcore_date),
            ))
        return RawLiveGameProgress(game_id, payload.get("Title") or f"Game #{game_id}", achievements)

    def get_user_progress(self, username: str, game_id: int) -> list[RawUnlockedAchievement]:
        """Unlock state for one account on one game. Softcore-only unlocks are included."""
        payload = self._client.get(
            "API_GetGameInfoAndUserProgress.php", {"u": username, "g": game_id}
        )
        unlocks = []
        for achievement_id, data in payload.get("Achievements", {}).items():
            date_hardcore = data.get("DateEarnedHardcore")
            date_softcore = data.get("DateEarned")
            unlocked_at_raw = date_hardcore or date_softcore
            if not unlocked_at_raw:
                continue
            unlocks.append(
                RawUnlockedAchievement(
                    achievement_id=int(achievement_id),
                    unlocked_at=parse_ra_datetime(unlocked_at_raw),
                    hardcore=bool(date_hardcore),
                )
            )
        return unlocks
