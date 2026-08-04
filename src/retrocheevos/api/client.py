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
            logger.exception("Request to %s failed", endpoint)
            raise RetroAchievementsAPIError(f"Request to {endpoint} failed") from error

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
