"""ListEntry DTO — maps to the `user_lists` table (Database.md 4.1)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.utils.enums import ListType


@dataclass
class ListEntry:
    account_id: int
    game_id: int
    list_type: ListType
    added_at: Optional[datetime] = None
    id: Optional[int] = None
