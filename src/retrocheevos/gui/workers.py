"""Background worker for running `services/` calls off the UI thread.

CodingStandards' threading model: network calls and heavy I/O must never run
on the UI thread. `services/` functions are plain, synchronous Python
(deliberately not Qt-aware, see sync_service.py's docstring) — this is the
`gui/`-side adapter that runs them on a QThread and turns results/errors/
progress into Qt signals the UI thread can safely connect to.
"""

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class ServiceWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)
    # For calls that produce results incrementally (e.g. one item fetched
    # at a time from several API calls) rather than all at once — lets the
    # GUI render items as they arrive instead of showing nothing until the
    # whole batch finishes. Same cross-thread-signal safety as `finished_ok`
    # (this class's `run()` executes on the worker thread; Qt's
    # AutoConnection queues delivery to whatever thread the receiver lives
    # on, same as every other signal here).
    partial_result = Signal(object)

    def __init__(
        self,
        func: Callable[..., Any],
        *args: Any,
        report_progress: bool = False,
        stream_results: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
        if report_progress:
            self._kwargs["progress_callback"] = self._emit_progress
        if stream_results:
            self._kwargs["result_callback"] = self._emit_partial_result

    def _emit_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)

    def _emit_partial_result(self, item: Any) -> None:
        self.partial_result.emit(item)

    def run(self) -> None:
        try:
            result = self._func(*self._args, **self._kwargs)
        except Exception as error:  # noqa: BLE001 — surfaced via `failed`, not swallowed
            self.failed.emit(str(error))
            return
        self.finished_ok.emit(result)
