"""GameCompletion DTO — per-account, per-game completion percentage.

Not part of the original Database.md schema — added (migration v3) to power
the Explorer Game Card's individual progress bar, sourced from
`NumAwarded`/`MaxPossible` via `API_GetUserCompletionProgress.php`.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class GameCompletion:
    account_id: int
    game_id: int
    percent_complete: float
    # RA's own award classification (RawAwardKind's value, e.g.
    # "beaten-hardcore"/"mastered") — None if the account has no award yet
    # for this game. Powers Explorer's already-beaten exclusion
    # (`get_finished_game_ids`).
    highest_award_kind: Optional[str] = None
    # Raw counts behind `percent_complete`, so progress can be shown as
    # "3/12 achievements" (Home's Events section). None for games whose
    # progress only ever arrived as a percentage.
    achievements_unlocked: Optional[int] = None
    achievements_total: Optional[int] = None
    last_synced_at: Optional[datetime] = None
