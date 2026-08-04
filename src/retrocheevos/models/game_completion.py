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
    last_synced_at: Optional[datetime] = None
