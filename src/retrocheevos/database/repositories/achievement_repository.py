"""Data access for `achievements` and `user_achievements` (Database.md 2.5, 2.6)."""

import sqlite3

from retrocheevos.database.serialization import datetime_to_sql
from retrocheevos.models.achievement import Achievement, UserAchievement


class AchievementRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_achievement(self, achievement: Achievement) -> None:
        """Insert or update an achievement. Ids come from RetroAchievements."""
        self._connection.execute(
            """
            INSERT INTO achievements (id, game_id, title, description, points, badge_path)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                points = excluded.points,
                badge_path = excluded.badge_path
            """,
            (
                achievement.id,
                achievement.game_id,
                achievement.title,
                achievement.description,
                achievement.points,
                achievement.badge_path,
            ),
        )

    def get_for_game(self, game_id: int) -> list[Achievement]:
        rows = self._connection.execute(
            "SELECT * FROM achievements WHERE game_id = ?", (game_id,)
        ).fetchall()
        return [self._row_to_achievement(row) for row in rows]

    def upsert_user_achievement(self, user_achievement: UserAchievement) -> UserAchievement:
        """Record/update one account's unlock state for one achievement."""
        self._connection.execute(
            """
            INSERT INTO user_achievements (account_id, achievement_id, unlocked_at, hardcore)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id, achievement_id) DO UPDATE SET
                unlocked_at = excluded.unlocked_at,
                hardcore = excluded.hardcore
            """,
            (
                user_achievement.account_id,
                user_achievement.achievement_id,
                datetime_to_sql(user_achievement.unlocked_at),
                user_achievement.hardcore,
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM user_achievements WHERE account_id = ? AND achievement_id = ?",
            (user_achievement.account_id, user_achievement.achievement_id),
        ).fetchone()
        user_achievement.id = row["id"]
        return user_achievement

    def get_mastered_game_ids(self, account_id: int) -> set[int]:
        """Game IDs where every achievement has been unlocked in hardcore mode.

        "Mastered" is defined here, at the query level, rather than stored
        redundantly — same principle as `installed_roms` deriving install
        status (Database.md 3.2).

        CURRENTLY ALWAYS EMPTY — do not use for filtering. It reads
        `achievements`/`user_achievements`, which are only written by
        `sync_service.sync_game_details`/`sync_account_progress`, and neither
        of those is called anywhere in the app. Explorer used to filter
        mastered games through here and silently excluded nothing as a
        result; it now uses
        `GameCompletionRepository.get_finished_game_ids`, which reads RA's
        own per-game award classification. Kept for when per-achievement
        syncing exists.
        """
        rows = self._connection.execute(
            """
            SELECT achievements.game_id FROM achievements
            LEFT JOIN user_achievements
                ON user_achievements.achievement_id = achievements.id
                AND user_achievements.account_id = ?
                AND user_achievements.hardcore = 1
            GROUP BY achievements.game_id
            HAVING COUNT(achievements.id) = COUNT(user_achievements.id)
                AND COUNT(achievements.id) > 0
            """,
            (account_id,),
        ).fetchall()
        return {row["game_id"] for row in rows}

    @staticmethod
    def _row_to_achievement(row: sqlite3.Row) -> Achievement:
        return Achievement(
            id=row["id"],
            game_id=row["game_id"],
            title=row["title"],
            description=row["description"],
            points=row["points"],
            badge_path=row["badge_path"],
        )
