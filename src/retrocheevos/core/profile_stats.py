"""Aggregates raw per-game completion progress into `ProfileStats`.

`api/profile.py`'s `RawGameProgress.highest_award_kind` is RetroAchievements'
own classification, confirmed against `API_GetUserCompletionProgress.php` —
no need to derive Beaten/Mastered from a completion percentage.

- Beaten: `highest_award_kind` is `beaten-hardcore` OR `beaten-softcore`.
  RA counts a game as beaten in either mode — that's the correct, general
  rule, kept even though hardcore-only accounts will only ever see
  `beaten-hardcore` in practice.
- Mastered: `highest_award_kind` is `mastered` (always hardcore, by RA's own
  definition).
- `completion_percentage`: mean of per-game `percent_complete` (see
  `core/game_completion.py`) across every game on the account's Completion
  Progress page — the same set `get_user_completion_progress()` returns, not
  only the ones with an award.
"""

from retrocheevos.api.profile import RawAwardKind, RawGameProgress, RawUserPoints
from retrocheevos.core.game_completion import compute_percent_complete
from retrocheevos.models.profile import ProfileStats

BEATEN_AWARD_KINDS = {RawAwardKind.BEATEN_HARDCORE, RawAwardKind.BEATEN_SOFTCORE}


def build_profile_stats(
    account_id: int,
    points: RawUserPoints,
    completion_progress: list[RawGameProgress],
) -> ProfileStats:
    games_beaten = sum(
        1 for game in completion_progress if game.highest_award_kind in BEATEN_AWARD_KINDS
    )
    games_mastered = sum(
        1 for game in completion_progress if game.highest_award_kind == RawAwardKind.MASTERED
    )
    percentages = [
        compute_percent_complete(game.num_awarded, game.max_possible)
        for game in completion_progress
    ]
    completion_percentage = sum(percentages) / len(percentages) if percentages else 0.0

    return ProfileStats(
        account_id=account_id,
        points=points.points,
        hardcore_points=points.hardcore_points,
        games_beaten=games_beaten,
        games_mastered=games_mastered,
        completion_percentage=completion_percentage,
    )
