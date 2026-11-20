"""Async game cover-art loader (Architecture.md — gui/ view logic only).

Wraps `QThreadPool` so a delegate can request a game's image without
blocking the UI thread (CodingStandards' threading model). Each request
runs `services.image_service.ensure_game_image_cached` on the pool, then
emits `image_ready` back on the GUI thread via Qt's automatic queued
connection (same cross-thread signal pattern as `gui/workers.py`'s
`ServiceWorker`).

Lifetime notes:

* Tasks (and the `_ImageLoadSignals` holder they own) are kept referenced
  until they actually finish. Dropping the last Python reference to a task
  mid-run would delete the signal source the worker thread is about to emit
  from, which is the "Signal source has been deleted" failure seen when a
  short-lived script exits with loads still in flight.
* `run()` always emits exactly one result, including when artwork lookup
  raises — otherwise the pending entry for that id would never be released
  and the image would never be retried.
* `forget_rom` bumps a per-ROM epoch so an in-flight load started before a
  ROM's file changed cannot repaint it with the old artwork. It is a no-op
  for user-picked covers, which are intentionally never deleted.
"""

import logging
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom
from retrocheevos.services.image_service import ensure_game_image_cached, ensure_rom_image_cached

logger = logging.getLogger(__name__)

# Bounded wait for pool tasks during shutdown. Cover downloads have their own
# HTTP timeout; this only stops the window close from waiting on the whole
# pool if a task is wedged.
SHUTDOWN_WAIT_MS = 2_000


class _ImageLoadSignals(QObject):
    # QRunnable isn't a QObject and can't own signals itself — this small
    # holder is the standard Qt pattern for emitting from inside one.
    # `epoch` lets the receiver reject a result for a request that was
    # invalidated (e.g. the ROM's file changed) while it was in flight.
    finished = Signal(int, int, object)  # id, epoch, Optional[QImage]


class _ImageLoadTask(QRunnable):
    def __init__(
        self, game: Game, epoch: int, signals: _ImageLoadSignals
    ) -> None:
        super().__init__()
        self._game = game
        self._epoch = epoch
        self._signals = signals

    def run(self) -> None:
        image: Optional[QImage] = None
        try:
            path = ensure_game_image_cached(self._game)
            if path is not None:
                candidate = QImage(str(path))
                if not candidate.isNull():
                    image = candidate
        except Exception:  # noqa: BLE001 — a failed cover must not kill the pool thread
            logger.exception("Could not load artwork for game %s", self._game.id)
        finally:
            try:
                self._signals.finished.emit(self._game.id, self._epoch, image)
            except Exception:  # noqa: BLE001
                logger.exception("Could not emit artwork result for game %s", self._game.id)


class _RomImageLoadTask(QRunnable):
    def __init__(
        self,
        rom: InstalledRom,
        cover_game: Optional[Game],
        epoch: int,
        signals: _ImageLoadSignals,
    ) -> None:
        super().__init__()
        self._rom = rom
        self._cover_game = cover_game
        self._epoch = epoch
        self._signals = signals

    def run(self) -> None:
        image: Optional[QImage] = None
        try:
            path = ensure_rom_image_cached(self._rom, self._cover_game)
            if path is not None:
                candidate = QImage(str(path))
                if not candidate.isNull():
                    image = candidate
        except Exception:  # noqa: BLE001 — a failed cover must not kill the pool thread
            logger.exception("Could not load artwork for ROM %s", self._rom.id)
        finally:
            try:
                self._signals.finished.emit(self._rom.id, self._epoch, image)
            except Exception:  # noqa: BLE001
                logger.exception("Could not emit artwork result for ROM %s", self._rom.id)


class ImageLoader(QObject):
    image_ready = Signal(int, object)  # game_id, Optional[QPixmap]
    rom_image_ready = Signal(int, object)  # installed_rom_id, Optional[QPixmap]

    def __init__(self) -> None:
        super().__init__()
        # id -> epoch of the request currently allowed to report. A missing
        # entry means "nothing pending"; an entry with a different epoch means
        # "that request was superseded".
        self._pending: dict[int, int] = {}
        self._rom_pending: dict[int, int] = {}
        # Keeps each task (and its signals object) alive for the duration of
        # the load — dropping the only Python reference before the background
        # thread finishes would be a use-after-free risk.
        self._tasks: set[QRunnable] = set()
        self._epochs: dict[tuple[str, int], int] = {}
        self._shutting_down = False

    def _epoch(self, kind: str, item_id: int) -> int:
        return self._epochs.get((kind, item_id), 0)

    def _bump_epoch(self, kind: str, item_id: int) -> int:
        epoch = self._epoch(kind, item_id) + 1
        self._epochs[(kind, item_id)] = epoch
        return epoch

    def forget_rom(self, rom_id: int) -> None:
        """Invalidate any artwork load already in flight for this ROM.

        Called after a scan detects that the file at a known path changed:
        the old request may still land and would otherwise repaint the card
        with artwork derived from the file that is no longer there. A new
        request can start immediately; the old one is ignored by epoch.
        """
        self._bump_epoch("rom", rom_id)
        self._rom_pending.pop(rom_id, None)

    def request_rom(self, rom: InstalledRom, cover_game: Optional[Game] = None) -> None:
        if self._shutting_down or rom.id in self._rom_pending:
            return
        epoch = self._epoch("rom", rom.id)
        signals = _ImageLoadSignals()
        signals.finished.connect(self._on_rom_finished)
        task = _RomImageLoadTask(rom, cover_game, epoch, signals)
        self._track(task, signals)
        self._rom_pending[rom.id] = epoch
        QThreadPool.globalInstance().start(task)

    def _on_rom_finished(self, rom_id: int, epoch: int, image: Optional[QImage]) -> None:
        if self._rom_pending.get(rom_id) != epoch:
            # Superseded by `forget_rom` (or by a newer request) — the result
            # describes artwork for a file that has since changed.
            return
        self._rom_pending.pop(rom_id, None)
        pixmap = QPixmap.fromImage(image) if image is not None else None
        self.rom_image_ready.emit(rom_id, pixmap)

    def request(self, game: Game) -> None:
        """Fire-and-forget: starts a background load unless one for this
        game is already in flight. Result arrives later via `image_ready`.
        """
        if self._shutting_down or game.id in self._pending:
            return

        epoch = self._epoch("game", game.id)
        signals = _ImageLoadSignals()
        signals.finished.connect(self._on_finished)
        task = _ImageLoadTask(game, epoch, signals)
        self._track(task, signals)
        self._pending[game.id] = epoch
        QThreadPool.globalInstance().start(task)

    def _track(self, task: QRunnable, signals: _ImageLoadSignals) -> None:
        self._tasks.add(task)
        # The lambda captures the task, so the signal holder keeps it alive
        # until the emission completes; then both are released.
        signals.finished.connect(lambda *_: self._tasks.discard(task))

    def _on_finished(self, game_id: int, epoch: int, image: Optional[QImage]) -> None:
        if self._pending.get(game_id) != epoch:
            return
        self._pending.pop(game_id, None)
        # Converted here, not in the worker thread — see `_ImageLoadTask.run`.
        pixmap = QPixmap.fromImage(image) if image is not None else None
        self.image_ready.emit(game_id, pixmap)

    def is_idle(self) -> bool:
        return not self._tasks

    def shutdown(self, timeout_ms: int = SHUTDOWN_WAIT_MS) -> None:
        """Stop accepting work and give in-flight pool tasks a bounded wait.

        Results that arrive after this are ignored (`_pending`/`_rom_pending`
        are cleared). The tasks themselves stay referenced: deleting a running
        QRunnable's signal source is exactly the failure this class avoids.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        self._pending.clear()
        self._rom_pending.clear()
        QThreadPool.globalInstance().waitForDone(timeout_ms)
