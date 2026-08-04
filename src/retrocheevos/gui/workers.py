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

    def __init__(
        self,
        func: Callable[..., Any],
        *args: Any,
        report_progress: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
        if report_progress:
            self._kwargs["progress_callback"] = self._emit_progress

    def _emit_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)

    def run(self) -> None:
        try:
            result = self._func(*self._args, **self._kwargs)
        except Exception as error:  # noqa: BLE001 — surfaced via `failed`, not swallowed
            self.failed.emit(str(error))
            return
        self.finished_ok.emit(result)
