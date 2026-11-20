"""Cooperative cancellation helpers shared by services and GUI workers.

Long operations are made of many small units (one API call, one file hash).
Cancellation is checked *between* units, never in the middle of one: an
in-flight HTTP request or file read is allowed to finish, then the loop stops
before starting the next unit. That keeps committed progress usable and avoids
interrupting SQLite writes halfway through a transaction.

`services/` stays Qt-agnostic: these are plain callables, and
`gui/workers.py::ServiceWorker` supplies its own `is_cancelled` bound method.
"""

import time
from typing import Callable, Optional

# How often a long wait re-checks the cancellation flag. Short enough that a
# close request is honoured promptly, long enough not to spin.
WAIT_POLL_SECONDS = 0.05


class OperationCancelled(Exception):
    """Raised between units of work after a cooperative stop was requested."""


def raise_if_cancelled(should_cancel: Optional[Callable[[], bool]]) -> None:
    """Abort the current operation if its owner asked it to stop."""
    if should_cancel is not None and should_cancel():
        raise OperationCancelled()


def interruptible_sleep(
    seconds: float, should_cancel: Optional[Callable[[], bool]]
) -> None:
    """Sleep, but wake up and raise `OperationCancelled` if asked to stop.

    Used for retry backoff: a plain `time.sleep(8)` in a rate-limited sync
    would keep the worker alive for the full wait even after the window was
    closed, which is exactly the shutdown delay this exists to remove.
    """
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        raise_if_cancelled(should_cancel)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(WAIT_POLL_SECONDS, remaining))
