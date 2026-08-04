"""User profile stats, completion progress, and awards (API.md §3).

`get_user_points` still follows the RetroAchievements Web API's shape from
memory, not a live-verified response — treat it as a first pass to confirm
during Services/GUI integration testing with a real API key.

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
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from retrocheevos.api.client import RetroAchievementsClient
from retrocheevos.api.serialization import parse_ra_datetime


@dataclass
class RawUserPoints:
    points: int
    hardcore_points: int


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


class ProfileClient:
    def __init__(self, client: RetroAchievementsClient) -> None:
        self._client = client

    def get_user_points(self, username: str) -> RawUserPoints:
        # NOTE: RA's "Points" field is already hardcore-only (softcore unlocks
        # accrue into a separate "SoftcorePoints" total on the real site) — but
        # this hasn't been confirmed against a live response, so `points` and
        # `hardcore_points` are both set from "Points" as a placeholder pending
        # verification, rather than guessing a distinct source for `points`.
        payload = self._client.get("API_GetUserPoints.php", {"u": username})
        return RawUserPoints(
            points=payload.get("Points", 0),
            hardcore_points=payload.get("Points", 0),
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
