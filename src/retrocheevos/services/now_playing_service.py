"""Refresh only the current game's achievements, rather than the whole catalog."""

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from retrocheevos.api.achievements import AchievementProgressClient
from retrocheevos.api.profile import ProfileClient
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.achievement_repository import AchievementRepository
from retrocheevos.database.repositories.game_completion_repository import GameCompletionRepository
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.models.account import Account
from retrocheevos.models.achievement import Achievement, UserAchievement
from retrocheevos.models.game_completion import GameCompletion
from retrocheevos.models.now_playing import LiveAchievement, NowPlayingSnapshot
from retrocheevos.services import play_session_service, session_service

RECENT_ACTIVITY_WINDOW = timedelta(minutes=10)


def refresh_now_playing(
    account: Account, stop_requested: Optional[Callable[[], bool]] = None
) -> Optional[NowPlayingSnapshot]:
    """At most two requests per refresh, limited to current account/game data.

    The API reports recent activity rather than an emulator's running state.
    Use the local launch while RA catches up. Newer RA activity can detect
    games switched within the same running emulator, including unmatched ROMs.
    """
    if account.id is None or (stop_requested is not None and stop_requested()):
        return None
    checked = datetime.now(timezone.utc)
    local = play_session_service.get_running_session(account.id)
    snapshot = NowPlayingSnapshot(
        account.id, local.game_id if local else None, local.title if local else '',
        active=local is not None, source='local' if local else 'retroachievements',
        checked_at=checked,
    )
    client = session_service.build_api_client(account)
    summary = ProfileClient(client).get_user_summary(account.username)
    if stop_requested is not None and stop_requested():
        return None
    last_seen = summary.last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    recent = bool(
        summary.last_game_id and last_seen is not None
        and timedelta(0) <= checked - last_seen <= RECENT_ACTIVITY_WINDOW
    )
    if recent and (local is None or last_seen >= local.started_at):
        snapshot.game_id = int(summary.last_game_id) if summary.last_game_id else None
        snapshot.title = summary.last_game_title or ''
        snapshot.presence = summary.rich_presence_msg or ''
        snapshot.active = True
        snapshot.source = 'retroachievements'
    if not snapshot.active:
        snapshot.notice = 'No recent game activity reported by RetroAchievements.'
        return snapshot
    if snapshot.game_id is None:
        snapshot.notice = 'Match this ROM to a catalog game to track its achievements.'
        return snapshot
    progress = AchievementProgressClient(client).get_live_game_progress(
        account.username, snapshot.game_id
    )
    if stop_requested is not None and stop_requested():
        return None
    snapshot.title = progress.title
    snapshot.achievements = [LiveAchievement(
        item.id, item.title, item.description, item.points, item.unlocked_at, item.hardcore
    ) for item in progress.achievements]
    if not snapshot.achievements:
        snapshot.notice = 'No achievement set is available for this game.'
    # A short write transaction after the network request. Deleting an
    # account during the fetch must not resurrect data or violate its FKs.
    with get_connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute('SELECT 1 FROM accounts WHERE id = ?', (account.id,)).fetchone() is None:
            return None
        if GameRepository(connection).get_by_id(snapshot.game_id) is not None:
            repository = AchievementRepository(connection)
            earned = 0
            for item in snapshot.achievements:
                repository.upsert_achievement(Achievement(
                    item.id, snapshot.game_id, item.title, item.description, item.points
                ))
                if item.unlocked_at is not None:
                    earned += 1
                    repository.upsert_user_achievement(UserAchievement(
                        account.id, item.id, item.hardcore, item.unlocked_at
                    ))
            total = len(snapshot.achievements)
            GameCompletionRepository(connection).upsert(GameCompletion(
                account.id, snapshot.game_id, 100.0 * earned / total if total else 0.0,
                achievements_unlocked=earned, achievements_total=total,
                last_synced_at=checked,
            ))
    return snapshot
