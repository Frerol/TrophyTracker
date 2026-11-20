"""Shared GUI-level state: which account is active right now.

This is view/session-state, not business logic (Architecture.md's "gui/ ...
view logic only") — it caches what `session_service` already knows and
notifies pages when it changes, so every page doesn't have to hit the
database just to know who's logged in.

It also owns the process-wide GUI resource registries: every `ServiceWorker`
and every `ImageLoader`. That gives shutdown one place to cancel background
work and wait for it, instead of each page holding its own worker references
and hoping the window is never closed mid-sync.
"""

from typing import Optional

from PySide6.QtCore import QObject, Signal

from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.workers import WorkerRegistry
from retrocheevos.models.account import Account
from retrocheevos.services import session_service


class AppContext(QObject):
    active_account_changed = Signal(object)  # Optional[Account]

    def __init__(self) -> None:
        super().__init__()
        self._active_account: Optional[Account] = session_service.get_active_account()
        self.workers = WorkerRegistry(self)
        self._image_loaders: list[ImageLoader] = []
        self._shutting_down = False

    @property
    def active_account(self) -> Optional[Account]:
        return self._active_account

    def refresh_active_account(self) -> None:
        self._active_account = session_service.get_active_account()
        self.active_account_changed.emit(self._active_account)

    def create_image_loader(self) -> ImageLoader:
        """Build an `ImageLoader` that shutdown will know about.

        Pages used to instantiate `ImageLoader()` directly, which left their
        pending pool tasks (and their signal holders) unaccounted for when the
        window closed.
        """
        loader = ImageLoader()
        self._image_loaders.append(loader)
        return loader

    def shutdown(self) -> None:
        """Cancel background work and wait for it in an orderly way.

        Idempotent: `MainWindow.closeEvent` and `aboutToQuit` can both call it.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        self.workers.shutdown()
        for loader in self._image_loaders:
            loader.shutdown()
