"""Per-account UI preferences (schema v18).

Everything the user adjusts and expects to find again next launch: window
state, cover sizes, and whatever comes later. Values are stored as TEXT and
coerced on the way out, so a caller asking for an int never has to handle a
malformed row — a bad value reads as "not set" and the default wins.

Every getter takes a default and every one of them tolerates *no active
account*. Preferences are read during window construction, which happens
before anything guarantees an account exists; returning the default there is
the whole point, not an edge case.
"""

import logging
from typing import Optional

from retrocheevos.database.connection import get_connection
from retrocheevos.services import session_service

logger = logging.getLogger(__name__)

# Window
KEY_WINDOW_MAXIMIZED = "window.maximized"
KEY_WINDOW_FULLSCREEN = "window.fullscreen"
KEY_WINDOW_WIDTH = "window.width"
KEY_WINDOW_HEIGHT = "window.height"
# Grids
KEY_LIBRARY_COVER_SIZE = "library.cover_size"
KEY_CONTINUE_PLAYING_COVER_SIZE = "continue_playing.cover_size"
# Updates — the release tag whose banner the user dismissed. Stores the
# *version*, not a boolean, so a later release notifies again on its own
# rather than needing something to remember to clear a flag.
KEY_DISMISSED_UPDATE_VERSION = "update.dismissed_version"


def _account_id() -> Optional[int]:
    account = session_service.get_active_account()
    return account.id if account is not None else None


def get_str(key: str, default: Optional[str] = None) -> Optional[str]:
    account_id = _account_id()
    if account_id is None:
        return default
    with get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM user_preferences WHERE account_id = ? AND key = ?",
            (account_id, key),
        ).fetchone()
    return row["value"] if row is not None else default


def set_str(key: str, value: str) -> None:
    """No-op when there's no active account — a preference with nobody to
    belong to is better dropped than attributed to whoever logs in next."""
    account_id = _account_id()
    if account_id is None:
        return
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (account_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT(account_id, key) DO UPDATE SET value = excluded.value
            """,
            (account_id, key, value),
        )


def get_int(key: str, default: int) -> int:
    raw = get_str(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Preference %s is not an int (%r); using default", key, raw)
        return default


def set_int(key: str, value: int) -> None:
    set_str(key, str(value))


def get_bool(key: str, default: bool) -> bool:
    raw = get_str(key)
    if raw is None:
        return default
    return raw == "1"


def set_bool(key: str, value: bool) -> None:
    set_str(key, "1" if value else "0")
