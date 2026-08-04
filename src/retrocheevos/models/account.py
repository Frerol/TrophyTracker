"""Account DTO — maps to the `accounts` table (Database.md 2.1)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Account:
    username: str
    api_key: str
    is_active: bool
    last_synced_at: Optional[datetime] = None
    id: Optional[int] = None
