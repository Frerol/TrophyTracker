"""Notification DTOs — map to `notifications` (Database.md 5.1)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.utils.enums import NotificationType


@dataclass
class Notification:
    account_id: int
    type: NotificationType
    message: str
    game_id: Optional[int] = None
    created_at: Optional[datetime] = None
    read: bool = False
    id: Optional[int] = None
