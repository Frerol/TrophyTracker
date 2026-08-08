"""Sync orchestration — the only place that combines `api/` calls with
`database/` writes (Architecture.md: GUI never talks to `api/` directly,
always via Services -> Core).

Every function here does real network I/O and must be called from a
background thread, never the UI thread (CodingStandards' threading model).
Progress on bulk operations is reported via a plain `progress_callback`
`(current, total) -> None` — a plain Python callable, not a Qt signal, so
this stays testable without a running Qt event loop; `gui/` wraps this in a
QThread and re-emits it as a Qt signal.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from retrocheevos.api.achievements import AchievementProgressClient
from retrocheevos.api.client import RetroAchievementsClient
from retrocheevos.api.exceptions import RateLimitError
from retrocheevos.api.games import GamesClient
from retrocheevos.api.profile import ProfileClient
from retrocheevos.core.game_completion import build_game_completions, compute_percent_complete
from retrocheevos.core.mapping import (
    map_achievement,
    map_badge,
    map_console,
    map_game,
    map_user_achievement,
)
from retrocheevos.core.profile_stats import build_profile_stats
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.account_repository import AccountRepository
from retrocheevos.database.repositories.achievement_repository import AchievementRepository
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.database.repositories.game_completion_repository import (
    GameCompletionRepository,
)
from retrocheevos.database.repositories.game_repository import (
    EVENTS_CONSOLE_ID,
    GameRepository,
)
from retrocheevos.database.repositories.profile_repository import ProfileRepository
from retrocheevos.models.account import Account
from retrocheevos.models.game import GameHash
from retrocheevos.models.game_completion import GameCompletion

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]
PhaseCallback = Callable[[str], None]

# How long cached profile_stats are trusted before an account
# activation/switch opportunistically re-syncs them — keeps repeated
# switches/restarts from hammering the API while still self-healing stale
# data (e.g. `true_points` left at its migration-v8 backfill default of 0)
# without needing a background timer.
PROFILE_SYNC_STALE_AFTER = timedelta(hours=6)

# Bump whenever `core/profile_stats.py` changes how beaten/mastered/
# completion are derived. Cached rows carrying an older revision are
# re-synced on the next account activation regardless of their age, so a
# corrected formula actually reaches the screen instead of waiting for the
# staleness window. Revision 1: paginated completion progress (was
# truncated at 100 games), mastered/completed now count as beaten, and
# completion is achievements-earned over achievements-available rather than
# an unweighted mean of per-game percentages.
# Revision 2: that last change was wrong. Completion is the site's "Average
# completion" — an unweighted mean again, but over all pages and with subsets
# excluded, which reproduces the site's 56.75 % exactly (see
# `core/profile_stats.py`).
PROFILE_STATS_REVISION = 2


def sync_consoles(client: RetroAchievementsClient) -> int:
    """Fetch the console list and cache it. Returns the number of consoles synced."""
    raw_consoles = _with_rate_limit_retry(
        "the console list", GamesClient(client).list_console_ids
    )
    with get_connection() as connection:
        repository = ConsoleRepository(connection)
        for raw_console in raw_consoles:
            repository.upsert(map_console(raw_console))
    logger.info("Synced %d consoles", len(raw_consoles))
    return len(raw_consoles)


def sync_games_for_console(
    client: RetroAchievementsClient,
    console_id: int,
    only_with_achievements: bool = True,
    progress_callback: Optional[ProgressCallback] = None,
) -> int:
    """Cache basic metadata for every game on a console (title/image/achievement count).

    Does not fetch median time or the achievement list — call `sync_game_details`
    per game for that; it's a heavier per-game request (API.md §4: fetch only
    what's needed).
    """
    raw_games = _with_rate_limit_retry(
        f"the game list for console {console_id}",
        lambda: GamesClient(client).list_games_for_console(
            console_id, only_with_achievements
        ),
    )
    now = datetime.now()
    total = len(raw_games)
    with get_connection() as connection:
        repository = GameRepository(connection)
        for index, raw_game in enumerate(raw_games, start=1):
            repository.upsert_game(map_game(raw_game, synced_at=now))
            if progress_callback:
                progress_callback(index, total)
    logger.info("Synced %d games for console %d", total, console_id)
    return total


# Confirmed live (see `services/activity_feed_service.py::API_CALL_DELAY_SECONDS`):
# RA's API has a short burst limiter — several back-to-back requests with no
# delay reliably return HTTP 429. `sync_full_catalog` makes one
# `API_GetGameList.php` call per console (~84 of them), so it paces them the
# same way that module already does.
CATALOG_SYNC_CALL_DELAY_SECONDS = 0.3
# Measured live: one request per 0.1s starts returning HTTP 429 after ~9
# calls, so the delay above is near the practical floor. These govern what
# happens when it trips anyway — doubling each time, so 1s, 2s, 4s.
RATE_LIMIT_BACKOFF_SECONDS = 1.0
MAX_RATE_LIMIT_RETRIES = 4


def sync_full_catalog(
    client: RetroAchievementsClient, progress_callback: Optional[ProgressCallback] = None
) -> int:
    """Lightweight sync of every console's game catalog — basic metadata and
    achievement counts only (no `sync_game_details`, which is a much heavier
    per-game request), so Explorer search has a complete, instant local
    catalog without per-console manual syncs.

    `progress_callback` reports (consoles synced so far, total consoles) —
    coarser than `sync_games_for_console`'s own per-game callback, which is
    intentionally not threaded through here.
    """
    sync_consoles(client)
    with get_connection() as connection:
        consoles = ConsoleRepository(connection).list_all()

    total_games = 0
    total_consoles = len(consoles)
    for index, console in enumerate(consoles, start=1):
        total_games += sync_games_for_console(client, console.id)
        if progress_callback:
            progress_callback(index, total_consoles)
        if index < total_consoles:
            time.sleep(CATALOG_SYNC_CALL_DELAY_SECONDS)

    logger.info(
        "Synced full catalog: %d games across %d consoles", total_games, total_consoles
    )
    return total_games


def sync_event_progress(
    client: RetroAchievementsClient,
    account: Account,
    progress_callback: Optional[ProgressCallback] = None,
) -> list[int]:
    """Fetches this account's per-event achievement counts, and reports which
    events are newly appeared since the last sync.

    RA models each community event as a game on the Events console, so the
    catalog sync already stores their titles/images/URLs — what it can't
    carry is per-account progress, which needs one
    `API_GetGameInfoAndUserProgress.php` call each (~237 today). Returns the
    game ids of events that had no local row before this run, for
    `services/notification_service.py` to turn into alerts.
    """
    with get_connection() as connection:
        known_event_ids = {
            event.id for event in GameRepository(connection).list_events()
        }

    sync_games_for_console(client, EVENTS_CONSOLE_ID)

    with get_connection() as connection:
        events = GameRepository(connection).list_events()
    new_event_ids = [event.id for event in events if event.id not in known_event_ids]

    games_client = GamesClient(client)
    now = datetime.now()
    total = len(events)
    for index, event in enumerate(events, start=1):
        try:
            # Retried on 429 before the broad catch below sees it. Without
            # this, a burst limit read as "this event failed" and skipped it
            # for the whole run — and being rate limited says nothing about
            # the event, so the next one in the loop would be skipped too.
            progress = _with_rate_limit_retry(
                f"progress for event {event.id}",
                lambda: games_client.get_user_game_progress(
                    account.username, event.id
                ),
            )
        except Exception as error:  # noqa: BLE001 — one bad event mustn't abort the rest
            logger.info("Skipped event %d progress: %s", event.id, error)
        else:
            with get_connection() as connection:
                GameCompletionRepository(connection).upsert(
                    GameCompletion(
                        account_id=account.id,
                        game_id=event.id,
                        percent_complete=compute_percent_complete(
                            progress.achievements_unlocked, progress.achievements_total
                        ),
                        achievements_unlocked=progress.achievements_unlocked,
                        achievements_total=progress.achievements_total,
                        last_synced_at=now,
                    )
                )
        if progress_callback:
            progress_callback(index, total)
        if index < total:
            time.sleep(CATALOG_SYNC_CALL_DELAY_SECONDS)

    logger.info(
        "Synced progress for %d events (%d new)", total, len(new_event_ids)
    )
    return new_event_ids


def sync_everything(
    client: RetroAchievementsClient,
    account: Account,
    progress_callback: Optional[ProgressCallback] = None,
    phase_callback: Optional[PhaseCallback] = None,
) -> list[int]:
    """One-click sync: catalog, then profile, then event progress.

    The order is load-bearing, not cosmetic. `sync_profile` drops completion
    rows for games it can't find locally, so running it before the catalog
    leaves beaten/mastered data missing — which in turn silently under-filters
    Explorer. Doing both from one action is what makes that ordering
    guaranteed rather than a thing the user has to know.

    Median times are deliberately NOT included: they cost one API call per
    game (~12k, roughly an hour), against ~3 minutes for everything here.
    They stay on their own per-console action.

    Returns the newly-detected event ids from the last phase.
    """
    if phase_callback:
        phase_callback("Catalog")
    sync_full_catalog(client, progress_callback)

    if phase_callback:
        phase_callback("Profile")
    sync_profile(client, account)

    if phase_callback:
        phase_callback("Events")
    return sync_event_progress(client, account, progress_callback)


def sync_median_times(
    client: RetroAchievementsClient,
    progress_callback: Optional[ProgressCallback] = None,
) -> int:
    """Backfills median time-to-beat across the whole browsable catalog.

    Separate from `sync_everything` because the data comes from a different,
    per-game endpoint (`API_GetGameProgression.php`) — `API_GetGameList.php`
    doesn't carry it — so this costs one paced request per game, on the order
    of an hour for a full catalog, against ~3 minutes for everything else.

    Only fetches games still missing the value, so an interrupted run resumes
    where it stopped and a second run over an already-filled catalog is
    nearly instant. Returns how many were filled in.
    """
    with get_connection() as connection:
        game_ids = GameRepository(connection).list_ids_missing_median_time()

    games_client = GamesClient(client)
    total = len(game_ids)
    filled = 0
    for index, game_id in enumerate(game_ids, start=1):
        progression = _fetch_median_time_with_retry(games_client, game_id)
        if progression is not None and progression.median_time_to_beat_hardcore_seconds is not None:
            with get_connection() as connection:
                GameRepository(connection).set_median_time(
                    game_id,
                    progression.median_time_to_beat_hardcore_seconds,
                    progression.times_used_in_hardcore_beat_median,
                )
            filled += 1
        if progress_callback:
            progress_callback(index, total)
        if index < total:
            time.sleep(CATALOG_SYNC_CALL_DELAY_SECONDS)

    logger.info("Synced median times: %d of %d games had a value", filled, total)
    return filled


def _with_rate_limit_retry(description: str, call):
    """Run `call()`, riding out RA's burst limiter with exponential backoff.

    The median-times loop had this protection and the catalog sync did not —
    so a single HTTP 429 aborted a first-time "Sync Everything" outright.
    That is the worst possible place for it: a brand-new account has the
    largest sync to do, over a thousand requests, and is therefore the most
    likely to trip the limiter and the least able to afford losing the run.

    Unlike `_fetch_median_time_with_retry`, exhausting the retries here
    **re-raises**. A missing median time is one blank cell; a missing console
    is a hole in the catalog that nothing later would notice or repair, so
    the caller has to hear about it.
    """
    delay = RATE_LIMIT_BACKOFF_SECONDS
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return call()
        except RateLimitError:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                logger.warning(
                    "Rate limited %d times on %s; giving up", attempt, description
                )
                raise
            logger.info(
                "Rate limited on %s (attempt %d) — waiting %.0fs",
                description,
                attempt,
                delay,
            )
            time.sleep(delay)
            delay *= 2
    return None


def _fetch_median_time_with_retry(games_client: GamesClient, game_id: int):
    """One game's median time, riding out RA's burst limiter.

    This loop runs for the better part of an hour on a full catalog, so a
    single HTTP 429 used to throw away the whole run — and the limiter is
    easy to trip: measured live, one request every 0.1s starts returning 429
    after about nine calls, which is why the pacing above stays at 0.3s.
    Backing off and retrying costs seconds; aborting costs the run.

    Returns None when a game can't be fetched at all, so the caller just
    skips it — `list_ids_missing_median_time` will offer it again next time.
    """
    delay = RATE_LIMIT_BACKOFF_SECONDS
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return games_client.get_median_time_to_beat_hardcore(game_id)
        except RateLimitError:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                logger.warning("Gave up on game %d after %d rate limits", game_id, attempt)
                return None
            time.sleep(delay)
            delay *= 2
        except Exception as error:  # noqa: BLE001 — one bad game mustn't kill the run
            logger.info("Skipped median time for game %d: %s", game_id, error)
            return None
    return None


def sync_game_details(client: RetroAchievementsClient, game_id: int) -> None:
    """Full sync for one game: metadata, achievements, hashes, median time to beat.

    Skips the upsert entirely if the game turns out to have zero achievements
    — games without an achievement set are never synced/stored at all
    (`database/repositories/game_repository.py`'s unconditional
    `has_achievements = 1` filter), so persisting one here would just leave a
    row nothing else in the app will ever surface, and no repository call to
    clean it back up later.
    """
    games_client = GamesClient(client)
    raw_game, raw_achievements = games_client.get_game_extended(game_id)

    if raw_game.num_achievements <= 0:
        logger.info("Skipped syncing game %d: no achievement set", game_id)
        return

    progression = games_client.get_median_time_to_beat_hardcore(game_id)
    hashes = games_client.get_game_hashes(game_id)
    now = datetime.now()

    with get_connection() as connection:
        game_repository = GameRepository(connection)
        achievement_repository = AchievementRepository(connection)

        game_repository.upsert_game(map_game(raw_game, progression, synced_at=now))
        for raw_achievement in raw_achievements:
            achievement_repository.upsert_achievement(map_achievement(raw_achievement))
        for rom_hash in hashes:
            game_repository.add_hash(GameHash(game_id=game_id, hash=rom_hash))

    logger.info(
        "Synced game %d: %d achievements, %d hashes", game_id, len(raw_achievements), len(hashes)
    )


def sync_account_progress(
    client: RetroAchievementsClient, account: Account, game_id: int
) -> None:
    """Sync one account's unlock state for one game.

    `user_achievements.achievement_id` has a foreign key to `achievements.id`
    — call `sync_game_details(game_id)` first so the achievement definitions
    exist locally. Unlocks for achievements not yet synced are skipped
    rather than crashing (same pattern as `sync_profile`).
    """
    unlocks = AchievementProgressClient(client).get_user_progress(account.username, game_id)
    with get_connection() as connection:
        repository = AchievementRepository(connection)
        known_achievement_ids = {a.id for a in repository.get_for_game(game_id)}
        skipped = 0
        for raw_unlock in unlocks:
            if raw_unlock.achievement_id not in known_achievement_ids:
                skipped += 1
                continue
            repository.upsert_user_achievement(map_user_achievement(account.id, raw_unlock))

    if skipped:
        logger.info(
            "Skipped %d unlock(s) for account %d, game %d: achievement not synced locally yet",
            skipped,
            account.id,
            game_id,
        )
    logger.info(
        "Synced %d unlocks for account %d, game %d", len(unlocks) - skipped, account.id, game_id
    )


def sync_profile(client: RetroAchievementsClient, account: Account) -> None:
    """Sync profile stats, per-game completion, and badges for one account.

    `game_completion.game_id` has a foreign key to `games.id`, and
    `API_GetUserCompletionProgress.php` doesn't return enough to create a
    valid `games` row (no console_id) — so completion rows for games not yet
    synced locally are skipped rather than crashing. `games_beaten` /
    `games_mastered` / `completion_percentage` are unaffected: they're
    computed from the raw completion progress directly, not from local
    `games` rows. Run `sync_consoles` + `sync_games_for_console` first (and
    re-run `sync_profile` after) to pick up completion % for those games too.
    """
    profile_client = ProfileClient(client)
    # Three back-to-back calls, retried and paced like the loops above. This
    # is the middle phase of `sync_everything`, so it arrives with ~84
    # catalog requests already spent — the burst limiter is warm here, not
    # idle, which made it the most likely phase to trip and the one whose
    # failure looks least like a rate limit ("Sync Everything failed").
    profile = _with_rate_limit_retry(
        "the user profile", lambda: profile_client.get_user_profile(account.username)
    )
    time.sleep(CATALOG_SYNC_CALL_DELAY_SECONDS)
    completion_progress = _with_rate_limit_retry(
        "completion progress",
        lambda: profile_client.get_user_completion_progress(account.username),
    )
    time.sleep(CATALOG_SYNC_CALL_DELAY_SECONDS)
    awards = _with_rate_limit_retry(
        "user awards", lambda: profile_client.get_user_awards(account.username)
    )
    now = datetime.now()

    stats = build_profile_stats(account.id, profile, completion_progress)
    stats.last_synced_at = now
    stats.stats_revision = PROFILE_STATS_REVISION
    completions = build_game_completions(account.id, completion_progress)
    for completion in completions:
        completion.last_synced_at = now

    with get_connection() as connection:
        ProfileRepository(connection).upsert_stats(stats)

        game_repository = GameRepository(connection)
        completion_repository = GameCompletionRepository(connection)
        skipped_game_ids = []
        for completion in completions:
            if game_repository.get_by_id(completion.game_id) is None:
                skipped_game_ids.append(completion.game_id)
                continue
            completion_repository.upsert(completion)

        events_console = ConsoleRepository(connection).get_by_name("Events")
        events_console_id = events_console.id if events_console else None

        profile_repository = ProfileRepository(connection)
        for raw_award in awards:
            profile_repository.upsert_badge(
                map_badge(account.id, raw_award, events_console_id=events_console_id)
            )

        AccountRepository(connection).update_last_synced(account.id, now)

    if skipped_game_ids:
        logger.info(
            "Skipped completion % for %d game(s) not yet synced locally (account %d): %s",
            len(skipped_game_ids),
            account.id,
            skipped_game_ids,
        )
    logger.info(
        "Synced profile for account %d: %d games tracked, %d awards",
        account.id,
        len(completion_progress),
        len(awards),
    )


def sync_profile_if_needed(client: RetroAchievementsClient, account: Account) -> bool:
    """Opportunistic profile sync for account activation/switch — self-heals
    stale cached points (e.g. `true_points` left at its migration-v8 backfill
    default of 0) without a background timer. Skips the network call if
    `profile_stats.last_synced_at` is still within `PROFILE_SYNC_STALE_AFTER`,
    so switching accounts repeatedly or restarting the app doesn't hammer the
    API. The manual "Sync Profile" button remains the explicit override.
    Returns whether a sync actually ran.

    Age is not the only thing that makes a cached row wrong: when the stats
    formula itself changes, every stored row is stale no matter how recently
    it was written. A row carrying an older `stats_revision` is therefore
    re-synced regardless of its timestamp — without that, corrected maths
    simply never reached the screen until the 6-hour window happened to pass.
    """
    with get_connection() as connection:
        stats = ProfileRepository(connection).get_stats(account.id)

    if (
        stats is not None
        and stats.stats_revision == PROFILE_STATS_REVISION
        and stats.last_synced_at is not None
        and datetime.now() - stats.last_synced_at < PROFILE_SYNC_STALE_AFTER
    ):
        return False

    sync_profile(client, account)
    return True
