"""Recent Activity feed rules (UI.md — Home screen). Pure logic, no I/O —
the actual API calls live in `services/activity_feed_service.py`.
"""

from retrocheevos.models.activity_feed import ActivityEntry


def build_activity_feed(entries: list[ActivityEntry]) -> list[ActivityEntry]:
    """Most recently active first; entries with no recent achievement (no
    activity in the lookback window) sort last, not dropped — RA's own
    Following page still lists everyone regardless of recency.
    """
    return sorted(entries, key=_sort_key)


def _sort_key(entry: ActivityEntry) -> tuple[bool, float]:
    has_activity = entry.last_achievement_at is not None
    timestamp = entry.last_achievement_at.timestamp() if has_activity else 0.0
    return (not has_activity, -timestamp)
