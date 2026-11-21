"""Recent Activity feed orchestration (UI.md — Home screen, RA
"Following"-page-style redesign; docs/archive/RoadmapHistory.md has the full
research trail).

Unlike every other `services/` module, this one is a **live read with no
DB writes** — it calls the API directly and returns fresh data each time.
Rich presence and "who's active right now" are ephemeral; caching them
into the local DB (the pattern every other module uses) would just show
stale status. `sync_service.py` remains the only module that writes to
the DB from API data — this one deliberately doesn't.

Every call here does real network I/O — run from a background thread,
never the UI thread (CodingStandards' threading model), same as
`sync_service.py`.

Each entry is built around the user's **last played game**
(`API_GetUserSummary.php`'s `LastGame`), not their last achievement unlock.
Those aren't the same thing — someone can play for hours without unlocking
anything — and the feed is about what people are doing. An earlier version
sourced the game from `API_GetUserRecentAchievements.php`; dropping that
call also took the per-user cost from 3 requests to 2.

`API_CALL_DELAY_SECONDS`: kept as an alias of the shared process-wide
`REQUEST_MIN_INTERVAL_SECONDS`. RA's API has a short burst limiter, not just
an hourly quota — 7-8 back-to-back requests with no delay reliably return
HTTP 429, while the same requests spaced ~0.3s apart don't. That pacing now
lives once in `api/client.py`'s `RequestPacer` rather than as a sleep in this
module, so it also covers the Home feed running alongside a catalog sync.
"""

import logging
from typing import Callable, Optional

from retrocheevos.api.client import REQUEST_MIN_INTERVAL_SECONDS
from retrocheevos.api.exceptions import AuthenticationError, RateLimitError
from retrocheevos.api.games import GamesClient
from retrocheevos.api.profile import ProfileClient
from retrocheevos.core.activity_feed import build_activity_feed
from retrocheevos.models.account import Account
from retrocheevos.models.activity_feed import ActivityEntry, ActivityFeedResult
from retrocheevos.services import image_service, session_service
from retrocheevos.utils.cancellation import OperationCancelled, raise_if_cancelled

logger = logging.getLogger(__name__)

FOLLOWED_USERS_LIMIT = 30
NO_ACTIVITY_STATUS_TEXT = "No recent activity"
API_CALL_DELAY_SECONDS = REQUEST_MIN_INTERVAL_SECONDS


def get_recent_activity_feed(
    account: Account,
    result_callback: Optional[Callable[[ActivityEntry], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ActivityFeedResult:
    """`result_callback`, if given, is called with each `ActivityEntry` as
    soon as it's built — this fetch is 3 real API calls deep per user and
    takes several seconds end to end (docs/archive/RoadmapHistory.md), so letting
    the caller render entries as they arrive (see `gui/workers.py`'s
    `stream_results`) makes it feel far faster than waiting for the whole
    batch, even though the total time is the same. The final result includes sorted entries and explicit partial-failure
    diagnostics. Authentication, rate limiting and cancellation propagate.
    """
    raise_if_cancelled(should_cancel)
    client = session_service.build_api_client(account)
    profile_client = ProfileClient(client)
    games_client = GamesClient(client)

    usernames = [account.username]
    following_unavailable = False
    try:
        usernames.extend(user.username for user in profile_client.get_users_i_follow(FOLLOWED_USERS_LIMIT))
    except (AuthenticationError, RateLimitError, OperationCancelled):
        raise
    except Exception:
        logger.warning("Could not fetch followed users", exc_info=True)
        following_unavailable = True

    entries = []
    failed_usernames = []
    seen = set()
    for username in usernames:
        raise_if_cancelled(should_cancel)
        if username.casefold() in seen:
            continue
        seen.add(username.casefold())
        try:
            entry = _build_entry(
                profile_client, games_client, username,
                is_self=(username.casefold() == account.username.casefold()),
                should_cancel=should_cancel,
            )
        except (AuthenticationError, RateLimitError, OperationCancelled):
            raise
        except Exception:
            logger.warning("Could not fetch activity for %s", username, exc_info=True)
            failed_usernames.append(username)
            continue
        if entry.progress_unavailable:
            failed_usernames.append(username)
        entries.append(entry)
        if result_callback is not None:
            result_callback(entry)
    return ActivityFeedResult(build_activity_feed(entries), failed_usernames, following_unavailable)


def _build_entry(
    profile_client: ProfileClient,
    games_client: GamesClient,
    username: str,
    is_self: bool,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ActivityEntry:
    raise_if_cancelled(should_cancel)
    summary = profile_client.get_user_summary(username)
    avatar_path = image_service.ensure_user_pic_cached(username, summary.user_pic_path)

    if summary.last_game_id is None:
        return ActivityEntry(
            username=username,
            is_self=is_self,
            avatar_path=avatar_path,
            status_text=summary.rich_presence_msg or NO_ACTIVITY_STATUS_TEXT,
            last_seen_at=summary.last_seen_at,
            game_title=None,
            game_console=None,
            game_icon_path=None,
            achievements_unlocked=None,
            achievements_total=None,
            playtime_seconds=None,
        )

    game_icon_path = image_service.ensure_activity_icon_cached(
        summary.last_game_id, summary.last_game_icon_path
    )
    unlocked, total, playtime_seconds, progress_unavailable = _get_game_progress(
        games_client, username, summary.last_game_id, should_cancel=should_cancel
    )

    return ActivityEntry(
        username=username,
        is_self=is_self,
        avatar_path=avatar_path,
        status_text=summary.rich_presence_msg or NO_ACTIVITY_STATUS_TEXT,
        last_seen_at=summary.last_seen_at,
        game_title=summary.last_game_title,
        game_console=summary.last_game_console,
        game_icon_path=game_icon_path,
        achievements_unlocked=unlocked,
        achievements_total=total,
        playtime_seconds=playtime_seconds,
        progress_unavailable=progress_unavailable,
    )


def _get_game_progress(
    games_client: GamesClient,
    username: str,
    game_id: int,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> tuple[Optional[int], Optional[int], Optional[int], bool]:
    raise_if_cancelled(should_cancel)
    try:
        progress = games_client.get_user_game_progress(username, game_id)
    except (AuthenticationError, RateLimitError, OperationCancelled):
        raise
    except Exception:
        logger.warning(
            "Could not fetch game progress for %s in game %d", username, game_id
        )
        return None, None, None, True
    return progress.achievements_unlocked, progress.achievements_total, progress.playtime_seconds, False
