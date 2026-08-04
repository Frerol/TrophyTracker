"""Async game cover-art loader (Architecture.md — gui/ view logic only).

Wraps `QThreadPool` so a delegate can request a game's image without
blocking the UI thread (CodingStandards' threading model). Each request
runs `services.image_service.ensure_game_image_cached` on the pool, then
emits `image_ready` back on the GUI thread via Qt's automatic queued
connection (same cross-thread signal pattern as `gui/workers.py`'s
`ServiceWorker`).
"""

from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from retrocheevos.models.game import Game
from retrocheevos.services.image_service import ensure_game_image_cached


class _ImageLoadSignals(QObject):
    # QRunnable isn't a QObject and can't own signals itself — this small
    # holder is the standard Qt pattern for emitting from inside one.
    finished = Signal(int, object)  # game_id, Optional[QImage]


class _ImageLoadTask(QRunnable):
    def __init__(self, game: Game, signals: _ImageLoadSignals) -> None:
        super().__init__()
        self._game = game
        self._signals = signals

    def run(self) -> None:
        path = ensure_game_image_cached(self._game)
        image: Optional[QImage] = None
        if path is not None:
            # QImage, not QPixmap: this runs on a QThreadPool worker
            # thread, and QPixmap wraps a native platform paint surface
            # that Qt only allows the GUI thread to touch — constructing
            # one here is a real (if intermittent) crash risk. QImage has
            # no such restriction; `_on_finished` converts it to a QPixmap
            # back on the GUI thread once it arrives via the queued signal.
            candidate = QImage(str(path))
            if not candidate.isNull():
                image = candidate
        self._signals.finished.emit(self._game.id, image)


class ImageLoader(QObject):
    image_ready = Signal(int, object)  # game_id, Optional[QPixmap]

    def __init__(self) -> None:
        super().__init__()
        # Also keeps each task (and its signals object) alive for the
        # duration of the load — dropping the only Python reference before
        # the background thread finishes would be a use-after-free risk.
        self._pending: dict[int, _ImageLoadTask] = {}

    def request(self, game: Game) -> None:
        """Fire-and-forget: starts a background load unless one for this
        game is already in flight. Result arrives later via `image_ready`.
        """
        if game.id in self._pending:
            return

        signals = _ImageLoadSignals()
        signals.finished.connect(self._on_finished)
        task = _ImageLoadTask(game, signals)
        self._pending[game.id] = task
        QThreadPool.globalInstance().start(task)

    def _on_finished(self, game_id: int, image: Optional[QImage]) -> None:
        self._pending.pop(game_id, None)
        # Converted here, not in the worker thread — see `_ImageLoadTask.run`.
        pixmap = QPixmap.fromImage(image) if image is not None else None
        self.image_ready.emit(game_id, pixmap)
