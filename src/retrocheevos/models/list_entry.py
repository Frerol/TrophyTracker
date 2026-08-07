"""ListEntry DTO — maps to the `user_lists` table (Database.md 4.1)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.utils.enums import ListType


@dataclass
class ListEntry:
    account_id: int
    game_id: int
    # Which list this row belongs to. `list_type` is only the predefined
    # slug, and is None for a list the user created — `list_id` is what
    # actually identifies the list (schema v15).
    list_id: int
    list_type: Optional[ListType] = None
    added_at: Optional[datetime] = None
    id: Optional[int] = None
