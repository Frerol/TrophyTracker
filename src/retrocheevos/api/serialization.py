"""Shared parsing helpers for RetroAchievements API responses."""

from datetime import datetime
from typing import Optional


def parse_ra_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a RetroAchievements timestamp.

    Uses `fromisoformat`, not a fixed `strptime` format — RA's timestamps
    aren't consistent across endpoints: some are space-separated with no
    timezone (`2024-01-01 10:00:00`), some are ISO 8601 with a `T` separator
    and a UTC offset (`2025-01-29T14:11:57+00:00`). `fromisoformat` accepts
    both.
    """
    return datetime.fromisoformat(value) if value else None
