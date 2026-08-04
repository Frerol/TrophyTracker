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
from datetime import datetime
from typing import Callable, Optional

from retrocheevos.api.achievements import AchievementProgressClient
from retrocheevos.api.client import RetroAchievementsClient
from retrocheevos.api.games import GamesClient
from retrocheevos.api.profile import ProfileClient
from retrocheevos.core.game_completion import build_game_completions
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
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.profile_repository import ProfileRepository
from retrocheevos.models.account import Account
from retrocheevos.models.game import GameHash

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


def sync_consoles(client: RetroAchievementsClient) -> int:
    """Fetch the console list and cache it. Returns the number of consoles synced."""
    raw_consoles = GamesClient(client).list_console_ids()
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
    raw_games = GamesClient(client).list_games_for_console(console_id, only_with_achievements)
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


def sync_game_details(client: RetroAchievementsClient, game_id: int) -> None:
    """Full sync for one game: metadata, achievements, hashes, median time to beat."""
    games_client = GamesClient(client)
    raw_game, raw_achievements = games_client.get_game_extended(game_id)
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
    points = profile_client.get_user_points(account.username)
    completion_progress = profile_client.get_user_completion_progress(account.username)
    awards = profile_client.get_user_awards(account.username)
    now = datetime.now()

    stats = build_profile_stats(account.id, points, completion_progress)
    stats.last_synced_at = now
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
