"""Shared GUI-level state: which account is active right now.

This is view/session-state, not business logic (Architecture.md's "gui/ ...
view logic only") — it caches what `session_service` already knows and
notifies pages when it changes, so every page doesn't have to hit the
database just to know who's logged in.
"""

from typing import Optional

from PySide6.QtCore import QObject, Signal

from retrocheevos.models.account import Account
from retrocheevos.services import session_service


class AppContext(QObject):
    active_account_changed = Signal(object)  # Optional[Account]

    def __init__(self) -> None:
        super().__init__()
        self._active_account: Optional[Account] = session_service.get_active_account()

    @property
    def active_account(self) -> Optional[Account]:
        return self._active_account

    def refresh_active_account(self) -> None:
        self._active_account = session_service.get_active_account()
        self.active_account_changed.emit(self._active_account)
