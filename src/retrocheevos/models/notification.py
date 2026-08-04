"""Notification DTOs — map to `notifications` and `notification_settings` (Database.md 5.1, 5.2)."""

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


@dataclass
class NotificationSetting:
    account_id: int
    type: NotificationType
    enabled: bool
