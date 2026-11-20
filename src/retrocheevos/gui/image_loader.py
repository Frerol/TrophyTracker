"""Async game cover-art loader (Architecture.md — gui/ view logic only).

Wraps `QThreadPool` so a delegate can request a game's image without
blocking the UI thread (CodingStandards' threading model). Each request
runs `services.image_service.ensure_game_image_cached` on the pool, then
emits `image_ready` back on the GUI thread via Qt's automatic queued
connection (same cross-thread signal pattern as `gui/workers.py`'s
`ServiceWorker`).
"""

from typing import Optional
import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom
from retrocheevos.services.image_service import ensure_game_image_cached, ensure_rom_image_cached

logger = logging.getLogger(__name__)


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


class _RomImageLoadTask(QRunnable):
    def __init__(self, rom: InstalledRom, cover_game: Optional[Game], signals: _ImageLoadSignals) -> None:
        super().__init__()
        self._rom = rom
        self._cover_game = cover_game
        self._signals = signals

    def run(self) -> None:
        image: Optional[QImage] = None
        try:
            path = ensure_rom_image_cached(self._rom, self._cover_game)
            if path is not None:
                candidate = QImage(str(path))
                if not candidate.isNull():
                    image = candidate
        except Exception:
            logger.exception("Could not load artwork for ROM %s", self._rom.id)
        self._signals.finished.emit(self._rom.id, image)


class ImageLoader(QObject):
    image_ready = Signal(int, object)  # game_id, Optional[QPixmap]
    rom_image_ready = Signal(int, object)  # installed_rom_id, Optional[QPixmap]

    def __init__(self) -> None:
        super().__init__()
        # Also keeps each task (and its signals object) alive for the
        # duration of the load — dropping the only Python reference before
        # the background thread finishes would be a use-after-free risk.
        self._pending: dict[int, _ImageLoadTask] = {}
        self._rom_pending: dict[int, _RomImageLoadTask] = {}

    def request_rom(self, rom: InstalledRom, cover_game: Optional[Game] = None) -> None:
        if rom.id in self._rom_pending:
            return
        signals = _ImageLoadSignals()
        signals.finished.connect(self._on_rom_finished)
        task = _RomImageLoadTask(rom, cover_game, signals)
        self._rom_pending[rom.id] = task
        QThreadPool.globalInstance().start(task)

    def _on_rom_finished(self, rom_id: int, image: Optional[QImage]) -> None:
        self._rom_pending.pop(rom_id, None)
        pixmap = QPixmap.fromImage(image) if image is not None else None
        self.rom_image_ready.emit(rom_id, pixmap)

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
