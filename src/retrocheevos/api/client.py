"""Low-level HTTP client for the RetroAchievements Web API (API.md §1-2).

This is the only place in the codebase that talks to retroachievements.org.
Never call this from `gui/` — always via `services/` -> `core/` (Architecture.md).
"""

import logging
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

REDACTED = "***"
# Below this length, replacing every occurrence would corrupt unrelated text
# more than it protects anything. A real RA key is 32 characters.
MIN_REDACTABLE_LENGTH = 8


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
            raise RateLimitError("RetroAchievements API rate limit exceeded")
        if not response.ok:
            raise RetroAchievementsAPIError(f"{endpoint} returned HTTP {response.status_code}")

        payload = response.json()
        if isinstance(payload, dict) and payload.get("Error"):
            raise RetroAchievementsAPIError(str(payload["Error"]))

        return payload
