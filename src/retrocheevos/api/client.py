"""Low-level HTTP client for the RetroAchievements Web API (API.md §1-2).

This is the only place in the codebase that talks to retroachievements.org.
Never call this from `gui/` — always via `services/` -> `core/` (Architecture.md).

**Shared request pacing.** RA enforces a short burst limiter on top of its
hourly quota. Pacing used to live in each service (`sync_service` slept 0.3s
between its calls, `activity_feed_service` did the same for its own), which
kept *each stream* polite but did nothing about two streams running at once —
a catalog sync plus Home's activity feed could easily double the request rate
and trip 429s for both. `RequestPacer` below is one process-wide budget: every
`RetroAchievementsClient.get` call, whichever service/thread issued it, waits
its turn. Per-service sleeps are gone; this is the single place pacing is
enforced, so adding a new API caller cannot forget it.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import requests

from retrocheevos.api.exceptions import (
    AuthenticationError,
    RateLimitError,
    RetroAchievementsAPIError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://retroachievements.org/API"
DEFAULT_TIMEOUT_SECONDS = 10

# Measured live: one request every 0.1s starts returning HTTP 429 after ~9
# calls; 0.3s apart does not. Shared by every caller — see the module docstring.
REQUEST_MIN_INTERVAL_SECONDS = 0.3
# A `Retry-After` longer than this is almost certainly a server-side quota
# window; waiting it out silently would look like a hang. The retry helper
# still backs off exponentially, so a bounded honouring of the hint is enough.
MAX_RETRY_AFTER_SECONDS = 120.0

REDACTED = "***"
# Below this length, replacing every occurrence would corrupt unrelated text
# more than it protects anything. A real RA key is 32 characters.
MIN_REDACTABLE_LENGTH = 8


class RequestPacer:
    """Process-wide minimum spacing between API requests.

    A plain monotonic deadline, not a token bucket: RA's limiter is about
    *bursts*, and the app only ever wants "no more than one request every
    `min_interval` seconds across every thread". `penalize` pushes the
    deadline out after a 429 so the next caller — whichever service it
    belongs to — waits too, instead of each stream discovering the limit on
    its own.
    """

    def __init__(self, min_interval_seconds: float = REQUEST_MIN_INTERVAL_SECONDS) -> None:
        self._min_interval = max(0.0, min_interval_seconds)
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    @property
    def min_interval_seconds(self) -> float:
        return self._min_interval

    def set_min_interval(self, seconds: float) -> None:
        """Test/configuration hook; production never changes this at runtime."""
        with self._lock:
            self._min_interval = max(0.0, seconds)

    def wait(self) -> None:
        """Block until the next request may start, then reserve that slot."""
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if self._next_allowed > now:
                time.sleep(self._next_allowed - now)
            self._next_allowed = time.monotonic() + self._min_interval

    def penalize(self, seconds: float) -> None:
        """Push every caller's next slot out after a rate-limit response."""
        if seconds <= 0:
            return
        with self._lock:
            self._next_allowed = max(
                self._next_allowed, time.monotonic() + seconds
            )

    def reset(self) -> None:
        with self._lock:
            self._next_allowed = 0.0


# The one budget every client shares.
pacer = RequestPacer()


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse a `Retry-After` header (delta-seconds or HTTP-date).

    Returns None for anything unparseable, so callers fall back to their own
    backoff rather than waiting forever on a malformed header.
    """
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = (when - datetime.now(timezone.utc)).total_seconds()
    if seconds < 0:
        return None
    return min(seconds, MAX_RETRY_AFTER_SECONDS)


def redact_credentials(text: str, secret: str) -> str:
    """Remove `secret` from text destined for a log or an error message.

    The API travels as a query parameter (`?z=user&y=<key>`), which means the
    key is inside every URL this client builds — and urllib3 puts the failing
    URL in its exception messages. So anything derived from a request error
    has to pass through here before it is written down.
    """
    if not secret or len(secret) < MIN_REDACTABLE_LENGTH:
        return text
    return text.replace(secret, REDACTED)


class RetroAchievementsClient:
    """Authenticated GET wrapper. Credentials are never logged."""

    def __init__(
        self, username: str, api_key: str, timeout: int = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._username = username
        self._api_key = api_key
        self._timeout = timeout
        self._session = requests.Session()

    def get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Perform an authenticated GET against `endpoint` and return the parsed JSON body."""
        request_params = {"z": self._username, "y": self._api_key}
        if params:
            request_params.update(params)

        url = f"{BASE_URL}/{endpoint}"
        logger.debug("GET %s", endpoint)

        pacer.wait()
        try:
            response = self._session.get(url, params=request_params, timeout=self._timeout)
        except requests.RequestException as error:
            # Was `logger.exception(...)`, which wrote the whole traceback —
            # and urllib3's message inside it reads "Max retries exceeded
            # with url: /API/X.php?z=user&y=<key>". That put the API key in
            # plaintext in logs/retrocheevos.log on every offline moment,
            # DNS hiccup or timeout, in the one file a user is most likely
            # to send someone when asking for help.
            detail = redact_credentials(str(error), self._api_key)
            logger.warning(
                "Request to %s failed: %s: %s", endpoint, type(error).__name__, detail
            )
            # `from None`, not `from error`: chaining keeps the original as
            # `__cause__`, and any outer handler logging with `exc_info` —
            # `main.py::_log_uncaught_exception` does exactly that — prints
            # the cause's traceback too, leaking the URL by the back door.
            # The useful part of the original is preserved above, redacted.
            raise RetroAchievementsAPIError(
                f"Request to {endpoint} failed: {type(error).__name__}: {detail}"
            ) from None

        if response.status_code == 401:
            raise AuthenticationError("Invalid RetroAchievements username or API key")
        if response.status_code == 429:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            if retry_after is not None:
                # Every caller shares this deadline, so one stream's 429
                # slows all of them down instead of each retrying blind.
                pacer.penalize(retry_after)
            raise RateLimitError(
                "RetroAchievements API rate limit exceeded", retry_after=retry_after
            )
        if not response.ok:
            raise RetroAchievementsAPIError(f"{endpoint} returned HTTP {response.status_code}")

        payload = response.json()
        if isinstance(payload, dict) and payload.get("Error"):
            raise RetroAchievementsAPIError(str(payload["Error"]))

        return payload
