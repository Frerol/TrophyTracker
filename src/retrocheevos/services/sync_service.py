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
from dataclasses import dataclass
import sqlite3
from datetime import datetime, timedelta
from typing import Callable, Optional

from retrocheevos.api.achievements import AchievementProgressClient
from retrocheevos.api.client import (
    REQUEST_MIN_INTERVAL_SECONDS,
    RetroAchievementsClient,
)
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
from retrocheevos.models.game_completion import GameCompletion
from retrocheevos.services import library_service
from retrocheevos.utils.enums import MetadataKind, MetadataFetchOutcome
from retrocheevos.utils.cancellation import (
    OperationCancelled,
    interruptible_sleep,
    raise_if_cancelled,
)

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


# Pacing used to live here as a per-loop `time.sleep`, which kept each sync
# polite in isolation but did nothing when Home's activity feed ran at the same
# time. It is now enforced once, process-wide, by `api/client.py`'s shared
# `RequestPacer`; this alias remains so the cost notes below and the tests that
# zero it keep a single named value to refer to.
CATALOG_SYNC_CALL_DELAY_SECONDS = REQUEST_MIN_INTERVAL_SECONDS
# Measured live: one request per 0.1s starts returning HTTP 429 after ~9
# calls, so the shared interval above is near the practical floor. These
# govern what happens when it trips anyway — doubling each time, so 1s, 2s, 4s
# — and honour a server-supplied `Retry-After` as a floor.
RATE_LIMIT_BACKOFF_SECONDS = 1.0
MAX_RATE_LIMIT_RETRIES = 4


def sync_consoles(
    client: RetroAchievementsClient,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> int:
    """Fetch the console list and cache it. Returns the number of consoles synced."""
    raise_if_cancelled(should_cancel)
    raw_consoles = _with_rate_limit_retry(
        "the console list",
        GamesClient(client).list_console_ids,
        should_cancel=should_cancel,
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
    should_cancel: Optional[Callable[[], bool]] = None,
) -> int:
    """Cache basic metadata for every game on a console (title/image/achievement count).

    Does not fetch median time or the achievement list — call `sync_game_details`
    per game for that; it's a heavier per-game request (API.md §4: fetch only
    what's needed).
    """
    raise_if_cancelled(should_cancel)
    raw_games = _with_rate_limit_retry(
        f"the game list for console {console_id}",
        lambda: GamesClient(client).list_games_for_console(
            console_id, only_with_achievements
        ),
        should_cancel=should_cancel,
    )
    now = datetime.now()
    total = len(raw_games)
    with get_connection() as connection:
        repository = GameRepository(connection)
        for index, raw_game in enumerate(raw_games, start=1):
            raise_if_cancelled(should_cancel)
            repository.upsert_game(map_game(raw_game, synced_at=now))
            if progress_callback:
                progress_callback(index, total)
    logger.info("Synced %d games for console %d", total, console_id)
    return total


def sync_full_catalog(
    client: RetroAchievementsClient,
    progress_callback: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> int:
    """Lightweight sync of every console's game catalog — basic metadata and
    achievement counts only (no `sync_game_details`, which is a much heavier
    per-game request), so Explorer search has a complete, instant local
    catalog without per-console manual syncs.

    `progress_callback` reports (consoles synced so far, total consoles) —
    coarser than `sync_games_for_console`'s own per-game callback, which is
    intentionally not threaded through here.
    """
    sync_consoles(client, should_cancel=should_cancel)
    with get_connection() as connection:
        consoles = ConsoleRepository(connection).list_all()

    total_games = 0
    total_consoles = len(consoles)
    for index, console in enumerate(consoles, start=1):
        raise_if_cancelled(should_cancel)
        total_games += sync_games_for_console(
            client, console.id, should_cancel=should_cancel
        )
        if progress_callback:
            progress_callback(index, total_consoles)

    logger.info(
        "Synced full catalog: %d games across %d consoles", total_games, total_consoles
    )
    return total_games


def _account_exists(account_id: int) -> bool:
    """Is this account still in the database?

    Long syncs carry an `Account` snapshot taken before they started, and
    Settings can delete that account mid-run. One indexed lookup against a
    loop that already spends 0.3s and an HTTP round trip per iteration.
    """
    with get_connection() as connection:
        return (
            connection.execute(
                "SELECT 1 FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            is not None
        )


def sync_event_progress(
    client: RetroAchievementsClient,
    account: Account,
    progress_callback: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
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

    sync_games_for_console(client, EVENTS_CONSOLE_ID, should_cancel=should_cancel)

    with get_connection() as connection:
        events = GameRepository(connection).list_events()
    new_event_ids = [event.id for event in events if event.id not in known_event_ids]

    games_client = GamesClient(client)
    now = datetime.now()
    total = len(events)
    for index, event in enumerate(events, start=1):
        raise_if_cancelled(should_cancel)
        # The account can be deleted while this loop runs. It takes ~237
        # requests at 0.3s, so it is live for over a minute, and nothing
        # stops it when Settings removes the account underneath it — the
        # `account` here is a snapshot taken before the run began. Writing a
        # `game_completion` for an id that no longer exists in `accounts`
        # fails the foreign key, which is what surfaced as "removing an
        # account crashes with FOREIGN KEY constraint failed" *after* the
        # removal itself had already succeeded.
        #
        # Stops the whole run rather than skipping one event: every
        # remaining iteration would fail the same way, and there is nothing
        # left to sync for an account that is gone.
        if not _account_exists(account.id):
            logger.info(
                "Event progress sync stopped at %d/%d: account %d was removed",
                index,
                total,
                account.id,
            )
            return new_event_ids
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
                should_cancel=should_cancel,
            )
        except OperationCancelled:
            raise
        except Exception as error:  # noqa: BLE001 — one bad event mustn't abort the rest
            logger.info("Skipped event %d progress: %s", event.id, error)
        else:
            try:
                with get_connection() as connection:
                    GameCompletionRepository(connection).upsert(
                        GameCompletion(
                            account_id=account.id,
                            game_id=event.id,
                            percent_complete=compute_percent_complete(
                                progress.achievements_unlocked,
                                progress.achievements_total,
                            ),
                            achievements_unlocked=progress.achievements_unlocked,
                            achievements_total=progress.achievements_total,
                            last_synced_at=now,
                        )
                    )
            except sqlite3.IntegrityError:
                # The check at the top of the loop can be beaten: the account
                # survives it, then the ~0.3s API call above gives the user
                # exactly the window they need to press Remove, and the write
                # lands against an id that is gone. No check can close that —
                # the state is only knowable at the moment of the write — so
                # the lost race is handled here rather than guarded against.
                #
                # Re-raised if the account is still there, because then the
                # foreign key failure means something else entirely and
                # swallowing it would hide a real bug.
                if _account_exists(account.id):
                    raise
                logger.info(
                    "Event progress sync stopped at %d/%d: account %d removed mid-write",
                    index,
                    total,
                    account.id,
                )
                return new_event_ids
        if progress_callback:
            progress_callback(index, total)

    logger.info(
        "Synced progress for %d events (%d new)", total, len(new_event_ids)
    )
    return new_event_ids


def sync_everything(
    client: RetroAchievementsClient,
    account: Account,
    progress_callback: Optional[ProgressCallback] = None,
    phase_callback: Optional[PhaseCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> list[int]:
    """One-click sync: catalog, then profile, then event progress.

    The order is load-bearing, not cosmetic. `sync_profile` drops completion
    rows for games it can't find locally, so running it before the catalog
    leaves beaten/mastered data missing — which in turn silently under-filters
    Explorer. Doing both from one action is what makes that ordering
    guaranteed rather than a thing the user has to know.

    Median times are deliberately NOT included: they cost one API call per
    game (~12k, so ~1h40 at the measured ~0.5s per request — see
    `sync_all_game_hashes`), against ~3 minutes for everything here. They
    stay on their own per-console action.

    Returns the newly-detected event ids from the last phase.
    """
    if phase_callback:
        phase_callback("Catalog")
    sync_full_catalog(client, progress_callback, should_cancel=should_cancel)

    raise_if_cancelled(should_cancel)
    if phase_callback:
        phase_callback("Profile")
    sync_profile(client, account, should_cancel=should_cancel)

    raise_if_cancelled(should_cancel)
    if phase_callback:
        phase_callback("Events")
    return sync_event_progress(
        client, account, progress_callback, should_cancel=should_cancel
    )


def sync_median_times(
    client: RetroAchievementsClient,
    progress_callback: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    force_refresh: bool = False,
) -> int:
    """Backfills median time-to-beat across the whole browsable catalog.

    Separate from `sync_everything` because the data comes from a different,
    per-game endpoint (`API_GetGameProgression.php`) — `API_GetGameList.php`
    doesn't carry it — so this costs one paced request per game, ~1h40 for a
    full catalog at the measured ~0.5s per request (see
    `sync_all_game_hashes`), against ~3 minutes for everything else.

    Only fetches games still missing the value, so an interrupted run resumes
    where it stopped and a second run over an already-filled catalog is
    nearly instant. Empty results expire after 30 days; force_refresh bypasses
    the selection cache. Failures are eligible immediately. Returns values filled.
    """
    with get_connection() as connection:
        game_ids = GameRepository(connection).list_ids_missing_median_time(force_refresh=force_refresh)

    games_client = GamesClient(client)
    total = len(game_ids)
    filled = 0
    for index, game_id in enumerate(game_ids, start=1):
        raise_if_cancelled(should_cancel)
        progression = _fetch_median_time_with_retry(
            games_client, game_id, should_cancel=should_cancel
        )
        with get_connection() as connection:
            repository = GameRepository(connection)
            if progression is None:
                repository.record_metadata_fetch(game_id, MetadataKind.MEDIAN_TIME, MetadataFetchOutcome.FAILED)
            else:
                seconds = progression.median_time_to_beat_hardcore_seconds
                repository.set_median_time(game_id, seconds, progression.times_used_in_hardcore_beat_median)
                repository.record_metadata_fetch(
                    game_id, MetadataKind.MEDIAN_TIME,
                    MetadataFetchOutcome.VALUE if seconds is not None else MetadataFetchOutcome.EMPTY,
                )
                if seconds is not None:
                    filled += 1
        if progress_callback:
            progress_callback(index, total)

    logger.info("Synced median times: %d of %d games had a value", filled, total)
    return filled


def _with_rate_limit_retry(
    description: str,
    call,
    should_cancel: Optional[Callable[[], bool]] = None,
):
    """Run `call()`, riding out RA's burst limiter with exponential backoff.

    The median-times loop had this protection and the catalog sync did not —
    so a single HTTP 429 aborted a first-time "Sync Everything" outright.
    That is the worst possible place for it: a brand-new account has the
    largest sync to do, over a thousand requests, and is therefore the most
    likely to trip the limiter and the least able to afford losing the run.

    A server-supplied `Retry-After` is honoured as a floor for the wait, so
    the retry never starts earlier than the server asked. `interruptible_sleep`
    lets a close request break out of the backoff immediately.

    Unlike `_fetch_median_time_with_retry`, exhausting the retries here
    **re-raises**. A missing median time is one blank cell; a missing console
    is a hole in the catalog that nothing later would notice or repair, so
    the caller has to hear about it.
    """
    delay = RATE_LIMIT_BACKOFF_SECONDS
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        raise_if_cancelled(should_cancel)
        try:
            return call()
        except RateLimitError as error:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                logger.warning(
                    "Rate limited %d times on %s; giving up", attempt, description
                )
                raise
            wait = max(delay, error.retry_after or 0.0)
            logger.info(
                "Rate limited on %s (attempt %d) — waiting %.0fs",
                description,
                attempt,
                wait,
            )
            interruptible_sleep(wait, should_cancel)
            delay *= 2
    return None


def _fetch_median_time_with_retry(
    games_client: GamesClient,
    game_id: int,
    should_cancel: Optional[Callable[[], bool]] = None,
):
    """One game's median time, riding out RA's burst limiter.

    This loop runs for well over an hour on a full catalog, so a
    single HTTP 429 used to throw away the whole run — and the limiter is
    easy to trip: measured live, one request every 0.1s starts returning 429
    after about nine calls, which is why the pacing above stays at 0.3s.
    Backing off and retrying costs seconds; aborting costs the run.

    Returns None when a game can't be fetched at all, so the caller just
    skips it — `list_ids_missing_median_time` will offer it again next time.
    """
    delay = RATE_LIMIT_BACKOFF_SECONDS
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        raise_if_cancelled(should_cancel)
        try:
            return games_client.get_median_time_to_beat_hardcore(game_id)
        except RateLimitError as error:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                logger.warning("Gave up on game %d after %d rate limits", game_id, attempt)
                return None
            interruptible_sleep(max(delay, error.retry_after or 0.0), should_cancel)
            delay *= 2
        except OperationCancelled:
            raise
        except Exception as error:  # noqa: BLE001 — one bad game mustn't kill the run
            logger.info("Skipped median time for game %d: %s", game_id, error)
            return None
    return None


def sync_game_details(
    client: RetroAchievementsClient,
    game_id: int,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> bool:
    """Full sync for one game: metadata, achievements, hashes, median time to beat.

    Skips the upsert entirely if the game turns out to have zero achievements
    — games without an achievement set are never synced/stored at all
    (`database/repositories/game_repository.py`'s unconditional
    `has_achievements = 1` filter), so persisting one here would just leave a
    row nothing else in the app will ever surface, and no repository call to
    clean it back up later.
    """
    raise_if_cancelled(should_cancel)
    games_client = GamesClient(client)
    # All three calls retried: this had none, and it is now reachable from a
    # ~36k-request backfill (`sync_all_game_hashes(full_details=True)`) where
    # tripping the burst limiter is a matter of when, not if.
    raw_game, raw_achievements = _with_rate_limit_retry(
        f"details for game {game_id}",
        lambda: games_client.get_game_extended(game_id),
        should_cancel=should_cancel,
    )

    if raw_game.num_achievements <= 0:
        logger.info("Skipped syncing game %d: no achievement set", game_id)
        return False

    raise_if_cancelled(should_cancel)
    progression = _with_rate_limit_retry(
        f"median time for game {game_id}",
        lambda: games_client.get_median_time_to_beat_hardcore(game_id),
        should_cancel=should_cancel,
    )
    raise_if_cancelled(should_cancel)
    hashes = _with_rate_limit_retry(
        f"hashes for game {game_id}",
        lambda: games_client.get_game_hashes(game_id),
        should_cancel=should_cancel,
    )
    now = datetime.now()

    with get_connection() as connection:
        game_repository = GameRepository(connection)
        achievement_repository = AchievementRepository(connection)

        game_repository.upsert_game(map_game(raw_game, progression, synced_at=now))
        for raw_achievement in raw_achievements:
            achievement_repository.upsert_achievement(map_achievement(raw_achievement))
        # `replace_hashes`, not a loop of `add_hash`: there is no unique
        # constraint on `(game_id, hash)`, so re-running this over a game
        # already synced used to append a second copy of every hash.
        game_repository.replace_hashes(game_id, hashes)
        game_repository.record_metadata_fetch(
            game_id, MetadataKind.HASHES,
            MetadataFetchOutcome.VALUE if hashes else MetadataFetchOutcome.EMPTY,
        )
        if progression is not None:
            seconds = progression.median_time_to_beat_hardcore_seconds
            game_repository.set_median_time(game_id, seconds, progression.times_used_in_hardcore_beat_median)
            game_repository.record_metadata_fetch(
                game_id, MetadataKind.MEDIAN_TIME,
                MetadataFetchOutcome.VALUE if seconds is not None else MetadataFetchOutcome.EMPTY,
            )

    logger.info(
        "Synced game %d: %d achievements, %d hashes", game_id, len(raw_achievements), len(hashes)
    )

    return bool(hashes)


@dataclass
class ConsoleHashSync:
    """What `sync_console_hashes` fetched and matched."""

    consoles: int
    games: int
    hashes: int
    matched: int


def sync_console_hashes(
    client: RetroAchievementsClient,
    console_ids: list[int],
    progress_callback: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ConsoleHashSync:
    """Fetch every game's ROM hashes for whole consoles — one request per
    console — then re-run matching for unmatched ROMs (R22).

    The fast path for automatic matching after a scan: `sync_all_game_hashes`
    asks game by game (~45 minutes for the consoles a typical user owns);
    this asks `API_GetGameList` with `h=1` once per console. Games are
    upserted first because `game_hashes` rows need their game. Cancellation
    keeps consoles already stored; matching still runs over what was fetched.
    """
    now = datetime.now()
    games = hashes = consoles = 0
    total = len(console_ids)
    try:
        for index, console_id in enumerate(console_ids, start=1):
            raise_if_cancelled(should_cancel)
            rows = _with_rate_limit_retry(
                f"the game hashes for console {console_id}",
                lambda cid=console_id: GamesClient(client).list_games_with_hashes(cid),
                should_cancel=should_cancel,
            )
            with get_connection() as connection:
                repository = GameRepository(connection)
                for raw_game, game_hashes in rows:
                    repository.upsert_game(map_game(raw_game, synced_at=now))
                    repository.replace_hashes(raw_game.id, game_hashes)
                    repository.record_metadata_fetch(
                        raw_game.id, MetadataKind.HASHES,
                        MetadataFetchOutcome.VALUE if game_hashes else MetadataFetchOutcome.EMPTY,
                    )
                    hashes += len(game_hashes)
            games += len(rows)
            consoles += 1
            if progress_callback:
                progress_callback(index, total)
    finally:
        matched = library_service.rematch_unmatched_roms()
    logger.info(
        "Console hash sync: %d console(s), %d games, %d hashes, %d ROM(s) matched",
        consoles, games, hashes, matched,
    )
    return ConsoleHashSync(consoles, games, hashes, matched)


def sync_all_game_hashes(
    client: RetroAchievementsClient,
    progress_callback: Optional[ProgressCallback] = None,
    full_details: bool = False,
    should_cancel: Optional[Callable[[], bool]] = None,
    force_refresh: bool = False,
) -> int:
    """Backfill ROM hashes across the catalog, so scanning a folder can match
    files to games by hash instead of leaving them unmatched.

    This is the missing half of ROM matching: `game_hashes` was only ever
    written by `sync_game_details`, which had no callers anywhere, so the
    table stayed empty and `find_game_id_by_hash` could never return a hit.
    Every scanned ROM landed unmatched.

    **Cost — measured, not derived from the pacing constant.** An earlier
    version of this docstring costed the run at `CATALOG_SYNC_CALL_DELAY_SECONDS`
    per request and claimed about an hour. That is wrong by roughly half:
    0.3s is the *sleep between* calls, and the HTTP round trip happens on top
    of it. Timed against the live API over 443 games, a `full_details=True`
    run averaged **1.26s per game** — three requests plus two sleeps, which
    puts the network round trip at ~0.22s and gives:

    ======================  ==================  ==============
    Mode                    Per game            Full ~11k queue
    ======================  ==================  ==============
    hashes only (default)   ~0.52s              **~1h40**
    full_details=True       ~1.26s              **~4h**
    ======================  ==================  ==============

    In practice the number that matters is smaller: `list_ids_missing_hashes`
    puts consoles you actually own ROMs for at the front, and that prefix was
    ~5k games — **about 45 minutes** — after which the rest is catalogue you
    have no files for and the run can simply be stopped.

    Those figures are one connection's, and latency is the dominant term, so
    treat them as the right order of magnitude rather than a guarantee. What
    is not connection-dependent is the ratio: `full_details=True` costs three
    times the requests for nothing ROM matching uses. Median times have their
    own backfill (`sync_median_times`) and achievements are not surfaced
    anywhere yet.

    **Resumable.** Works off `list_ids_missing_hashes`, so stopping and
    re-running picks up where it left off rather than starting over — the
    whole reason that query exists.

    Empty responses are remembered for 30 days; force_refresh re-fetches all
    browsable games. Failed attempts remain immediately retryable.

    Returns the number of games that got at least one hash. Games that fail
    are skipped, not fatal: over 12k requests something will go wrong, and
    losing hours of progress to one bad game would be absurd.
    """
    with get_connection() as connection:
        game_ids = GameRepository(connection).list_ids_missing_hashes(force_refresh=force_refresh)

    games_client = GamesClient(client)
    total = len(game_ids)
    synced = 0
    logger.info(
        "Hash backfill starting: %d games missing hashes (full_details=%s)",
        total,
        full_details,
    )

    for index, game_id in enumerate(game_ids, start=1):
        raise_if_cancelled(should_cancel)
        try:
            if full_details:
                if sync_game_details(client, game_id, should_cancel=should_cancel):
                    synced += 1
            else:
                hashes = _with_rate_limit_retry(
                    f"hashes for game {game_id}",
                    lambda: games_client.get_game_hashes(game_id),
                    should_cancel=should_cancel,
                )
                with get_connection() as connection:
                    repository = GameRepository(connection)
                    repository.replace_hashes(game_id, hashes)
                    repository.record_metadata_fetch(
                        game_id, MetadataKind.HASHES,
                        MetadataFetchOutcome.VALUE if hashes else MetadataFetchOutcome.EMPTY,
                    )
                if hashes:
                    synced += 1
        except OperationCancelled:
            raise
        except Exception as error:  # noqa: BLE001 — one bad game mustn't kill the run
            logger.info("Skipped hashes for game %d: %s", game_id, error)
            with get_connection() as connection:
                GameRepository(connection).record_metadata_fetch(
                    game_id, MetadataKind.HASHES, MetadataFetchOutcome.FAILED
                )

        if progress_callback:
            progress_callback(index, total)

    # The point of the whole run. Without this the newly-fetched hashes sit
    # unused: matching only happens at scan time, and a rescan deliberately
    # skips files already recorded, so ROMs scanned before the backfill would
    # stay unmatched forever. Costs no API calls — the hashes are already on
    # the rows.
    matched = library_service.rematch_unmatched_roms()
    logger.info(
        "Hash backfill finished: %d of %d games got hashes, %d ROM(s) newly matched",
        synced,
        total,
        matched,
    )
    return synced


def sync_account_progress(
    client: RetroAchievementsClient,
    account: Account,
    game_id: int,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> None:
    """Sync one account's unlock state for one game.

    `user_achievements.achievement_id` has a foreign key to `achievements.id`
    — call `sync_game_details(game_id)` first so the achievement definitions
    exist locally. Unlocks for achievements not yet synced are skipped
    rather than crashing (same pattern as `sync_profile`).
    """
    raise_if_cancelled(should_cancel)
    unlocks = AchievementProgressClient(client).get_user_progress(account.username, game_id)
    raise_if_cancelled(should_cancel)
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


def sync_profile(
    client: RetroAchievementsClient,
    account: Account,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> None:
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
    raise_if_cancelled(should_cancel)
    profile = _with_rate_limit_retry(
        "the user profile",
        lambda: profile_client.get_user_profile(account.username),
        should_cancel=should_cancel,
    )
    raise_if_cancelled(should_cancel)
    completion_progress = _with_rate_limit_retry(
        "completion progress",
        lambda: profile_client.get_user_completion_progress(account.username),
        should_cancel=should_cancel,
    )
    raise_if_cancelled(should_cancel)
    awards = _with_rate_limit_retry(
        "user awards",
        lambda: profile_client.get_user_awards(account.username),
        should_cancel=should_cancel,
    )
    now = datetime.now()

    # Same hazard as the event loop: the three requests above take a second
    # or so, and Settings can delete the account in that window. Checked
    # here, immediately before the write, rather than at the top of the
    # function — a check before the network calls proves nothing about the
    # state when the write finally lands.
    if not _account_exists(account.id):
        logger.info("Profile sync discarded: account %d was removed", account.id)
        return

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


def sync_profile_if_needed(
    client: RetroAchievementsClient,
    account: Account,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> bool:
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

    sync_profile(client, account, should_cancel=should_cancel)
    return True
