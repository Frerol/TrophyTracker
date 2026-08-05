"""User profile stats, completion progress, and awards (API.md §3).

`get_user_profile` (`API_GetUserProfile.php`) is confirmed via a live call:
returns `UserPic` (a path fragment, e.g. `/UserPic/{username}.png` — same
base URL as game images, `library/game_images.py`'s
`https://i.retroachievements.org`, also confirmed live), `TotalPoints`
(identical value to the older `API_GetUserPoints.php`'s `Points`, which
this replaces — one call now covers points, true points, and the photo
instead of two), and `TotalTruePoints` (RetroRatio-weighted total, shown
alongside points on RA's own site).

`get_user_awards` (`API_GetUserAwards.php`) is now confirmed via a live
call: `VisibleUserAwards` items include `Title`, `ImageIcon`, `AwardedAt`,
`AwardType` (e.g. `"Game Beaten"`, `"Mastery/Completion"` — observed
values; RA's own top-level `EventAwardsCount`/`SiteAwardsCount` counters
imply further values this account had none of to observe directly), and
`ConsoleID`. See `core/mapping.py::map_badge` for how `AwardType`/
`ConsoleID` decide `Badge.is_event`.

`get_user_completion_progress` (`API_GetUserCompletionProgress.php`) is
confirmed: it returns `HighestAwardKind`, `NumAwarded`, and `MaxPossible` per
game — every game on the account's Completion Progress page, not just ones
with an award.

Deriving `games_beaten` / `games_mastered` / `completion_percentage` (from
`HighestAwardKind`) and per-game `percent_complete` (from
`NumAwarded`/`MaxPossible`) is a `core/` decision (Architecture.md — "what
counts as Completed"), not done here.

`get_users_i_follow` (`API_GetUsersIFollow.php`) and `get_recent_achievements`
(`API_GetUserRecentAchievements.php`) are both confirmed live for the Recent
Activity redesign (DevelopmentRoadmap.md): `API_GetUserProfile.php` and
`API_GetUserRecentAchievements.php` both also work with `u=<any username>`,
not just the authenticated account — confirmed by calling them against a
followed user, not just self.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from retrocheevos.api.client import RetroAchievementsClient
from retrocheevos.api.serialization import parse_ra_datetime


@dataclass
class RawUserProfile:
    points: int
    hardcore_points: int
    true_points: int
    user_pic_path: Optional[str]
    rich_presence_msg: Optional[str] = None
    last_game_id: Optional[int] = None


class RawAwardKind(str, Enum):
    """RetroAchievements' own per-game award tiers (`HighestAwardKind`)."""

    BEATEN_SOFTCORE = "beaten-softcore"
    BEATEN_HARDCORE = "beaten-hardcore"
    COMPLETED = "completed"
    MASTERED = "mastered"


@dataclass
class RawGameProgress:
    game_id: int
    title: str
    highest_award_kind: Optional[RawAwardKind]
    num_awarded: Optional[int]
    max_possible: Optional[int]


@dataclass
class RawAward:
    title: str
    image_path: Optional[str]
    awarded_at: Optional[datetime]
    # Confirmed via a live call this session (the two fields above were
    # previously the only ones read from this response): `AwardType` is
    # RA's per-award category ("Game Beaten", "Mastery/Completion", and
    # presumably "Event"/site-award variants — this account had none of
    # those to observe directly). `ConsoleID` is included as a
    # cross-check against the Events console (Database.md — `core/mapping.py`).
    award_type: Optional[str]
    console_id: Optional[int]


@dataclass
class RawFollowedUser:
    username: str
    ulid: str
    points: int
    softcore_points: int
    is_following_me: bool


@dataclass
class RawRecentAchievement:
    unlocked_at: Optional[datetime]
    game_id: int
    game_title: str
    game_icon_path: Optional[str]
    console_name: Optional[str]
    points: int
    true_ratio: int


class ProfileClient:
    def __init__(self, client: RetroAchievementsClient) -> None:
        self._client = client

    def get_user_profile(self, username: str) -> RawUserProfile:
        # NOTE: RA's "TotalPoints" is already hardcore-only (softcore
        # unlocks accrue into the separate "TotalSoftcorePoints", confirmed
        # live as 0 for the account this was tested against — real but
        # unexercised) — `points`/`hardcore_points` both set from
        # "TotalPoints" as before, that part of the original guess held up.
        payload = self._client.get("API_GetUserProfile.php", {"u": username})
        return RawUserProfile(
            points=payload.get("TotalPoints", 0),
            hardcore_points=payload.get("TotalPoints", 0),
            true_points=payload.get("TotalTruePoints", 0),
            user_pic_path=payload.get("UserPic"),
            rich_presence_msg=payload.get("RichPresenceMsg"),
            last_game_id=payload.get("LastGameID"),
        )

    def get_user_completion_progress(self, username: str) -> list[RawGameProgress]:
        payload = self._client.get("API_GetUserCompletionProgress.php", {"u": username})
        # Defensive: paginated RA endpoints commonly wrap results in "Results",
        # but a bare list is handled too in case this one doesn't.
        items = payload.get("Results", []) if isinstance(payload, dict) else payload

        progress = []
        for item in items:
            raw_kind = item.get("HighestAwardKind")
            progress.append(
                RawGameProgress(
                    game_id=item["GameID"],
                    title=item["Title"],
                    highest_award_kind=RawAwardKind(raw_kind) if raw_kind else None,
                    num_awarded=item.get("NumAwarded"),
                    max_possible=item.get("MaxPossible"),
                )
            )
        return progress

    def get_user_awards(self, username: str) -> list[RawAward]:
        payload = self._client.get("API_GetUserAwards.php", {"u": username})
        awards = []
        for item in payload.get("VisibleUserAwards", []):
            awards.append(
                RawAward(
                    title=item.get("Title", ""),
                    image_path=item.get("ImageIcon"),
                    awarded_at=parse_ra_datetime(item.get("AwardedAt")),
                    award_type=item.get("AwardType"),
                    console_id=item.get("ConsoleID"),
                )
            )
        return awards

    def get_users_i_follow(self, limit: int = 30) -> list[RawFollowedUser]:
        payload = self._client.get("API_GetUsersIFollow.php", {"c": limit, "o": 0})
        followed = []
        for item in payload.get("Results", []):
            followed.append(
                RawFollowedUser(
                    username=item["User"],
                    ulid=item.get("ULID", ""),
                    points=item.get("Points", 0),
                    softcore_points=item.get("PointsSoftcore", 0),
                    is_following_me=bool(item.get("IsFollowingMe", False)),
                )
            )
        return followed

    def get_recent_achievements(
        self, username: str, minutes: int
    ) -> list[RawRecentAchievement]:
        payload = self._client.get(
            "API_GetUserRecentAchievements.php", {"u": username, "m": minutes}
        )
        achievements = []
        for item in payload:
            achievements.append(
                RawRecentAchievement(
                    unlocked_at=parse_ra_datetime(item.get("Date")),
                    game_id=item["GameID"],
                    game_title=item.get("GameTitle", ""),
                    game_icon_path=item.get("GameIcon"),
                    console_name=item.get("ConsoleName"),
                    points=item.get("Points", 0),
                    true_ratio=item.get("TrueRatio", 0),
                )
            )
        return achievements
