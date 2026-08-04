"""Translates raw API responses (`api/`) into persistence DTOs (`models/`).

This is the one place allowed to know about both shapes — `api/` stays
ignorant of `models/`, and `database/` stays ignorant of `api/`
(Architecture.md's layering).
"""

from datetime import datetime
from typing import Optional

from retrocheevos.api.achievements import RawUnlockedAchievement
from retrocheevos.api.games import RawAchievementDefinition, RawConsole, RawGame, RawGameProgression
from retrocheevos.api.profile import RawAward
from retrocheevos.core.game_classification import classify_game_type
from retrocheevos.models.achievement import Achievement, UserAchievement
from retrocheevos.models.console import Console
from retrocheevos.models.game import Game
from retrocheevos.models.profile import Badge

RETROACHIEVEMENTS_GAME_URL_TEMPLATE = "https://retroachievements.org/game/{game_id}"


def map_console(raw_console: RawConsole) -> Console:
    return Console(id=raw_console.id, name=raw_console.name)


def map_game(
    raw_game: RawGame,
    progression: Optional[RawGameProgression] = None,
    synced_at: Optional[datetime] = None,
) -> Game:
    return Game(
        id=raw_game.id,
        title=raw_game.title,
        console_id=raw_game.console_id,
        has_achievements=raw_game.num_achievements > 0,
        image_path=raw_game.image_icon_path,
        game_type=classify_game_type(raw_game.title),
        median_time_to_beat_hardcore_seconds=(
            progression.median_time_to_beat_hardcore_seconds if progression else None
        ),
        times_used_in_hardcore_beat_median=(
            progression.times_used_in_hardcore_beat_median if progression else None
        ),
        retroachievements_url=RETROACHIEVEMENTS_GAME_URL_TEMPLATE.format(game_id=raw_game.id),
        last_synced_at=synced_at,
    )


def map_achievement(raw: RawAchievementDefinition) -> Achievement:
    return Achievement(
        id=raw.id,
        game_id=raw.game_id,
        title=raw.title,
        description=raw.description,
        points=raw.points,
        badge_path=raw.badge_name,
    )


def map_user_achievement(account_id: int, raw: RawUnlockedAchievement) -> UserAchievement:
    return UserAchievement(
        account_id=account_id,
        achievement_id=raw.achievement_id,
        unlocked_at=raw.unlocked_at,
        hardcore=raw.hardcore,
    )


def map_badge(account_id: int, raw: RawAward) -> Badge:
    return Badge(
        account_id=account_id,
        name=raw.title,
        image_path=raw.image_path,
        owned=True,
        progress=None,
    )
