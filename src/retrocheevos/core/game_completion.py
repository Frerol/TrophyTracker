"""Per-game completion percentage, from `NumAwarded`/`MaxPossible`, plus RA's
own per-game award classification (`highest_award_kind`).

Shared by `core/profile_stats.py` (average/count across all games) and the
Explorer Game Card (individual progress bar, via `GameCompletionRepository`).
`highest_award_kind` also powers Explorer's already-beaten exclusion
(`GameCompletionRepository.get_finished_game_ids`).
"""

from typing import Optional

from retrocheevos.api.profile import RawGameProgress
from retrocheevos.models.game_completion import GameCompletion


def compute_percent_complete(num_awarded: Optional[int], max_possible: Optional[int]) -> float:
    """0% when there's no achievement data to compute from (missing or zero MaxPossible)."""
    if not max_possible:
        return 0.0
    return 100 * (num_awarded or 0) / max_possible


def build_game_completions(
    account_id: int, completion_progress: list[RawGameProgress]
) -> list[GameCompletion]:
    """One `GameCompletion` per game on the account's Completion Progress page."""
    return [
        GameCompletion(
            account_id=account_id,
            game_id=game.game_id,
            percent_complete=compute_percent_complete(game.num_awarded, game.max_possible),
            highest_award_kind=game.highest_award_kind.value if game.highest_award_kind else None,
        )
        for game in completion_progress
    ]
