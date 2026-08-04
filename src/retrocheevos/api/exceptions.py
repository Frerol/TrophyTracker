"""Exceptions raised by the RetroAchievements API client."""


class RetroAchievementsAPIError(Exception):
    """Base exception for any failure talking to the RetroAchievements API."""


class AuthenticationError(RetroAchievementsAPIError):
    """Raised when the configured username/API key is rejected."""


class RateLimitError(RetroAchievementsAPIError):
    """Raised when the API responds with HTTP 429."""
