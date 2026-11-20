"""Application-wide coordination for jobs that write the same local tables.

Before this, each page protected only itself: Explorer disabled its own sync
buttons while its own worker ran, and Home/Settings/Library each did the same
for their own actions. Nothing stopped two *different* pages — or Home's
embedded Explorer and the standalone one — from starting conflicting jobs at
the same time. Two catalog syncs, or a scan racing a hash backfill, write the
same SQLite tables from separate threads; that is both a request-rate problem
and a write-contention problem.

The rule is deliberately coarse: every job listed here is mutually exclusive
with every other one. They all touch the same catalog/library tables, and the
app has no use for running two of them at once. Read-only work (Recent
Activity, Now Playing) is not coordinated here — it shares the API budget in
`api/client.py`, which is the part that matters for rate limiting.

This module is plain Python (no Qt) so `services/` stays framework-agnostic.
The GUI acquires a token before starting a worker and releases it when the
worker reports done/failed/cancelled. Listeners are plain callables; the GUI
happens to call them on the UI thread, which is where every acquire/release
below originates.
"""

import logging
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Optional

logger = logging.getLogger(__name__)

Listener = Callable[[Optional[str]], None]

# Human-readable names for the jobs the GUI starts. Kept here so every page
# names the same operation the same way in its conflict message.
JOB_SYNC_EVERYTHING = "Sync Everything"
JOB_SYNC_HASHES = "Sync ROM hashes"
JOB_SYNC_MEDIAN_TIMES = "Sync median times"
JOB_SYNC_PROFILE = "Sync profile"
JOB_SCAN_FOLDER = "Scan ROM folder"
JOB_SCAN_ALL_FOLDERS = "Scan all ROM folders"
JOB_REHASH_LIBRARY = "Re-hash library"


@dataclass(frozen=True)
class JobToken:
    """Proof of ownership; only the token that started a job can end it."""

    name: str
    sequence: int


class JobConflictError(RuntimeError):
    """Raised when a caller insists on a job while another one is active."""

    def __init__(self, requested: str, active: str) -> None:
        super().__init__(
            f"{requested} cannot start while {active} is running. "
            "Wait for it to finish and try again."
        )
        self.requested = requested
        self.active = active


_lock = Lock()
_active: Optional[JobToken] = None
_sequence = 0
_listeners: list[Listener] = []


def active_job() -> Optional[str]:
    with _lock:
        return _active.name if _active is not None else None


def try_acquire(name: str) -> Optional[JobToken]:
    """Reserve the app-wide job slot, or return None if another job owns it."""
    global _active, _sequence
    with _lock:
        if _active is not None:
            logger.info("Job %r refused: %r is already running", name, _active.name)
            return None
        _sequence += 1
        _active = JobToken(name=name, sequence=_sequence)
        token = _active
    logger.info("Job %r started", name)
    _notify(name)
    return token


def acquire(name: str) -> JobToken:
    """Reserve the slot or raise `JobConflictError` — for callers that report."""
    token = try_acquire(name)
    if token is not None:
        return token
    raise JobConflictError(name, active_job() or "another job")


def release(token: Optional[JobToken]) -> None:
    """Release the slot if `token` still owns it.

    Tokens make this idempotent and safe against a late callback from an
    older worker: only the current owner can clear the slot.
    """
    global _active
    if token is None:
        return
    with _lock:
        if _active != token:
            return
        _active = None
    logger.info("Job %r finished", token.name)
    _notify(None)


def subscribe(listener: Listener) -> Callable[[], None]:
    """Register a state listener; returns an unsubscribe callable."""
    with _lock:
        _listeners.append(listener)
    return lambda: _unsubscribe(listener)


def _unsubscribe(listener: Listener) -> None:
    with _lock:
        if listener in _listeners:
            _listeners.remove(listener)


def _notify(name: Optional[str]) -> None:
    # Copied under the lock, called outside it: a listener that acquires or
    # releases a job must not deadlock on the registry's own lock.
    with _lock:
        listeners = list(_listeners)
    for listener in listeners:
        try:
            listener(name)
        except Exception:  # noqa: BLE001 — a bad listener must not break job control
            logger.exception("Job coordinator listener failed")


def reset() -> None:
    """Test hook: clear the slot and listeners between isolated tests."""
    global _active
    with _lock:
        _active = None
        _listeners.clear()
