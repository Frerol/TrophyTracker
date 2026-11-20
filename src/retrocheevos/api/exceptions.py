"""Exceptions raised by the RetroAchievements API client."""

from typing import Optional


class RetroAchievementsAPIError(Exception):
    """Base exception for any failure talking to the RetroAchievements API."""


class AuthenticationError(RetroAchievementsAPIError):
    """Raised when the configured username/API key is rejected."""


class RateLimitError(RetroAchievementsAPIError):
    """Raised when the API responds with HTTP 429.

    `retry_after` carries the server's own guidance (the `Retry-After`
    header), in seconds, when it supplied one. Callers use it as a floor for
    their backoff instead of guessing: retrying earlier than the server asked
    is what turns a single rate-limited call into a retry storm.
    """

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
