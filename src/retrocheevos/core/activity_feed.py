"""Recent Activity feed rules (UI.md — Home screen). Pure logic, no I/O —
the actual API calls live in `services/activity_feed_service.py`.
"""

from datetime import datetime

from retrocheevos.models.activity_feed import ActivityEntry

# Fixed reference for turning a timestamp into a sortable number. The
# timestamps are naive UTC (see `api/profile.py`), and `datetime.timestamp()`
# would read them as *local* time — harmless while every entry shares the
# same offset, but it makes the ordering depend on the machine's timezone for
# no reason. Subtracting a constant keeps the arithmetic in the same clock
# the values are already in.
_SORT_EPOCH = datetime(1970, 1, 1)


def build_activity_feed(entries: list[ActivityEntry]) -> list[ActivityEntry]:
    """Most recently active first; entries with no known activity sort last,
    not dropped — RA's own Following page still lists everyone regardless of
    recency.

    Ordered by `last_seen_at` (when they were last playing), matching the
    Following page. An earlier version ordered by last *unlock*, which pushed
    anyone mid-session but not currently unlocking anything down the list and
    read as the feed being stale.
    """
    return sorted(entries, key=_sort_key)


def _sort_key(entry: ActivityEntry) -> tuple[bool, float]:
    moment = entry.last_seen_at
    if moment is None:
        return (True, 0.0)
    return (False, -(moment - _SORT_EPOCH).total_seconds())
