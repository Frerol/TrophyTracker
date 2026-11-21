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
Activity redesign (docs/archive/RoadmapHistory.md): `API_GetUserProfile.php` and
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

# `API_GetUserCompletionProgress.php` caps a response at 100 rows whatever
# you ask for, so this is the page size the pagination loop steps by.
COMPLETION_PROGRESS_PAGE_SIZE = 100


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
class RawUserSummary:
    user_pic_path: Optional[str]
    rich_presence_msg: Optional[str]
    last_seen_at: Optional[datetime]
    # The game they were last playing — from `LastGame`, not from their most
    # recent unlock. The two usually agree and don't have to: someone can
    # play for hours without unlocking anything, and the activity feed is
    # about what they're *doing*.
    last_game_id: Optional[int]
    last_game_title: Optional[str]
    last_game_console: Optional[str]
    last_game_icon_path: Optional[str]


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

    def get_user_summary(self, username: str) -> RawUserSummary:
        """Everything `get_user_profile` gives, plus **"Last seen"**.

        `API_GetUserProfile.php` has no "when was this person last playing"
        field at all, which is why the activity feed had been falling back to
        the last *achievement unlock* and reading up to 16 hours behind the
        site. This endpoint has it, confirmed live against a followed user
        the site listed as "Last seen 06 Aug 2026, 17:21":

            RichPresenceMsgDate      = 2026-08-06 17:31:50
            RecentlyPlayed[0].LastPlayed = 2026-08-06 17:31:50
            LastActivity.lastupdate  = None   <- do not use, always null

        Both live fields agree; `RichPresenceMsgDate` is read here because it
        is a flat field rather than the first element of a list that is empty
        for a user who has never played. `LastActivity` looks like the
        obvious candidate and is a dead end — every one of its keys came back
        null.

        `last_seen_at` is returned **naive, exactly as RA sends it** — that
        is UTC, and it is displayed unconverted by deliberate choice so the
        app reads the same as the site. See `widgets/activity_entry_card.py`.
        """
        payload = self._client.get(
            "API_GetUserSummary.php", {"u": username, "g": 1, "a": 1}
        )
        last_game = payload.get("LastGame") or {}
        return RawUserSummary(
            user_pic_path=payload.get("UserPic"),
            rich_presence_msg=payload.get("RichPresenceMsg"),
            last_seen_at=parse_ra_datetime(payload.get("RichPresenceMsgDate")),
            last_game_id=payload.get("LastGameID"),
            last_game_title=last_game.get("Title"),
            last_game_console=last_game.get("ConsoleName"),
            last_game_icon_path=last_game.get("ImageIcon"),
        )

    def get_user_completion_progress(self, username: str) -> list[RawGameProgress]:
        """Every game this account has any progress on — all pages of them.

        This endpoint caps a response at 100 games and reports the real
        number in `Total`. Reading only the first page silently truncated
        the data every profile statistic is derived from (confirmed live:
        100 returned, `Total` 147), so points/beaten/mastered/completion
        were all computed from roughly two thirds of the account.
        """
        items: list = []
        offset = 0
        while True:
            payload = self._client.get(
                "API_GetUserCompletionProgress.php",
                {"u": username, "c": COMPLETION_PROGRESS_PAGE_SIZE, "o": offset},
            )
            # Defensive: a bare list is handled too, in case the shape ever
            # changes back — in that case there's no pagination to follow.
            if not isinstance(payload, dict):
                items.extend(payload)
                break

            page = payload.get("Results", [])
            items.extend(page)
            total = payload.get("Total")
            offset += len(page)
            if not page or total is None or offset >= total:
                break

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
        """`unlocked_at` comes back naive, exactly as RA sends it.

        That value is **UTC** — proven by cross-checking the same unlock
        against `API_GetUserAwards.php`, which timestamps it explicitly:
        award `2026-08-05T10:11:40+00:00` for game 757 is the same event
        this endpoint reports as `2026-08-05 10:11:40`, no offset applied.
        It is left naive and displayed unconverted by deliberate choice, so
        the app shows the same wall-clock numbers as the RA site (which also
        renders UTC). See `widgets/activity_entry_card.py`.

        Ordering is *not* assumed — RA does return newest-first (confirmed
        live: 84 rows, strictly descending), but that isn't documented, so
        `activity_feed_service` picks the latest by timestamp instead of
        by position.
        """
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
