"""Background workers for running `services/` calls off the UI thread.

CodingStandards' threading model: network calls and heavy I/O must never run
on the UI thread. `services/` functions are plain, synchronous Python
(deliberately not Qt-aware, see sync_service.py's docstring) — this is the
`gui/`-side adapter that runs them on a QThread and turns results/errors/
progress into Qt signals the UI thread can safely connect to.

**Cooperative cancellation.** A `ServiceWorker` created with
`cancellable=True` passes its own `is_cancelled` bound method into the target
as `should_cancel`. Services check it between units of work (one API call, one
file hash) and raise `utils.cancellation.OperationCancelled`, which surfaces
as the `cancelled` signal rather than a failure. This is what makes closing
the window during a sync stop the loop promptly instead of leaving it running
for the rest of the catalogue.

**Ownership.** A QThread whose only reference is dropped while `run()` is
still executing is destroyed mid-run — undefined behaviour, and the cause of
a native crash this app has already hit once. `WorkerRegistry` keeps every
started worker alive until it actually finishes, and `shutdown()` cancels and
waits for them in an orderly way.
"""

import logging
import time
from threading import Event
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

from retrocheevos.utils.cancellation import OperationCancelled

logger = logging.getLogger(__name__)

# How long `WorkerRegistry.shutdown` waits in total for workers to stop.
# Cancellation is checked between units of work, so this only has to cover
# one in-flight HTTP call (10s timeout) in the worst case; the normal path is
# a fraction of a second. Kept below the request timeout so a wedged request
# cannot hold the window open indefinitely.
SHUTDOWN_TIMEOUT_MS = 5_000


class ServiceWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    # Emitted instead of `finished_ok`/`failed` when `cancel()` was requested
    # and the operation stopped at a safe boundary. Separate from `failed`
    # because "the user closed the window" is not an error to show in a dialog.
    cancelled = Signal()
    progress = Signal(int, int)
    # For calls that produce results incrementally (e.g. one item fetched
    # at a time from several API calls) rather than all at once — lets the
    # GUI render items as they arrive instead of showing nothing until the
    # whole batch finishes. Same cross-thread-signal safety as `finished_ok`
    # (this class's `run()` executes on the worker thread; Qt's
    # AutoConnection queues delivery to whatever thread the receiver lives
    # on, same as every other signal here).
    partial_result = Signal(object)
    # A label for what the call is doing right now, for operations made of
    # several distinct stages (see `sync_service.sync_everything`). Separate
    # from `progress` because that one carries only two ints and is already
    # consumed by several pages — this is additive, so those are untouched.
    phase = Signal(str)

    def __init__(
        self,
        func: Callable[..., Any],
        *args: Any,
        report_progress: bool = False,
        stream_results: bool = False,
        report_phase: bool = False,
        cancellable: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._cancel_requested = Event()
        self._cancellable = cancellable
        if report_progress:
            self._kwargs["progress_callback"] = self._emit_progress
        if stream_results:
            self._kwargs["result_callback"] = self._emit_partial_result
        if report_phase:
            self._kwargs["phase_callback"] = self._emit_phase
        if cancellable:
            self._kwargs["should_cancel"] = self.is_cancelled

    def _emit_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)

    def _emit_partial_result(self, item: Any) -> None:
        self.partial_result.emit(item)

    def _emit_phase(self, label: str) -> None:
        self.phase.emit(label)

    def cancel(self) -> None:
        """Ask the operation to stop at its next safe boundary."""
        if self._cancel_requested.is_set():
            return
        logger.info("Cancellation requested for %s", getattr(self._func, "__name__", self._func))
        self._cancel_requested.set()
        self.requestInterruption()

    def is_cancelled(self) -> bool:
        return self._cancel_requested.is_set()

    @property
    def cancellable(self) -> bool:
        return self._cancellable

    def run(self) -> None:
        try:
            result = self._func(*self._args, **self._kwargs)
        except OperationCancelled:
            logger.info("Worker stopped at a cancellation boundary")
            self.cancelled.emit()
            return
        except Exception as error:  # noqa: BLE001 — surfaced via `failed`, not swallowed
            if self.is_cancelled():
                # A request in flight during shutdown can fail for reasons
                # that are consequences of shutting down; report it as a
                # cancellation, not as something the user should fix.
                logger.info("Worker stopped after cancellation: %s", error)
                self.cancelled.emit()
                return
            self.failed.emit(str(error))
            return
        if self.is_cancelled():
            self.cancelled.emit()
            return
        self.finished_ok.emit(result)


class WorkerRegistry(QObject):
    """Owns every `ServiceWorker` the GUI starts.

    Holding a reference until `finished` is emitted is not bookkeeping — it is
    what prevents Qt from destroying a running QThread. The registry also
    gives shutdown one place to cancel everything and one bounded wait.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        # worker -> optional key, used to answer "is a worker for X running?"
        self._workers: dict[ServiceWorker, Any] = {}
        self._shutdown = False

    def start(self, worker: ServiceWorker, key: Any = None) -> ServiceWorker:
        """Start `worker` and keep it alive until it finishes."""
        if self._shutdown:
            # A late navigation callback after the window started closing
            # must not spawn a new thread that nothing will wait for.
            logger.info("Worker refused: registry is shutting down")
            worker.cancel()
            return worker
        self._workers[worker] = key
        worker.finished.connect(lambda: self._forget(worker))
        worker.start()
        return worker

    def _forget(self, worker: ServiceWorker) -> None:
        self._workers.pop(worker, None)
        worker.deleteLater()

    def has_key(self, key: Any) -> bool:
        return any(existing == key for existing in self._workers.values())

    def cancel_key(self, key: Any) -> None:
        for worker, existing in list(self._workers.items()):
            if existing == key:
                worker.cancel()

    def cancel_all(self) -> None:
        for worker in list(self._workers):
            worker.cancel()

    def active(self) -> tuple[ServiceWorker, ...]:
        return tuple(self._workers)

    def shutdown(self, timeout_ms: int = SHUTDOWN_TIMEOUT_MS) -> None:
        """Cancel and wait for every worker, bounded by `timeout_ms` in total.

        Workers that do not stop in time are left alive (referenced by the
        module-level `_LINGERING_WORKERS` set) rather than destroyed while
        running, which is what Qt aborts the process over.
        """
        self._shutdown = True
        self.cancel_all()
        remaining_ms = max(0, timeout_ms)
        for worker in list(self._workers):
            if remaining_ms <= 0:
                break
            if not worker.isRunning():
                continue
            started = _monotonic_ms()
            worker.wait(remaining_ms)
            remaining_ms -= max(0, _monotonic_ms() - started)
        survivors = [worker for worker in self._workers if worker.isRunning()]
        if survivors:
            logger.warning(
                "%d worker(s) still running after shutdown timeout; "
                "keeping them referenced until they finish",
                len(survivors),
            )
            _LINGERING_WORKERS.update(survivors)


# Stragglers must stay referenced: dropping the last Python reference to a
# running QThread destroys it and aborts the process. They are normally empty;
# this only matters when a request outlives the shutdown budget.
_LINGERING_WORKERS: set[ServiceWorker] = set()


def _monotonic_ms() -> float:
    return time.monotonic() * 1000
