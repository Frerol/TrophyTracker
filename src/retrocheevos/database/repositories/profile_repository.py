"""Data access for `profile_stats` and `badges` (Database.md 6.1, 6.2)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.profile import Badge, ProfileStats


class ProfileRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_stats(self, stats: ProfileStats) -> None:
        self._connection.execute(
            """
            INSERT INTO profile_stats (
                account_id, points, hardcore_points, games_beaten,
                games_mastered, completion_percentage, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                points = excluded.points,
                hardcore_points = excluded.hardcore_points,
                games_beaten = excluded.games_beaten,
                games_mastered = excluded.games_mastered,
                completion_percentage = excluded.completion_percentage,
                last_synced_at = excluded.last_synced_at
            """,
            (
                stats.account_id,
                stats.points,
                stats.hardcore_points,
                stats.games_beaten,
                stats.games_mastered,
                stats.completion_percentage,
                datetime_to_sql(stats.last_synced_at),
            ),
        )

    def get_stats(self, account_id: int) -> Optional[ProfileStats]:
        row = self._connection.execute(
            "SELECT * FROM profile_stats WHERE account_id = ?", (account_id,)
        ).fetchone()
        return self._row_to_stats(row) if row else None

    def upsert_badge(self, badge: Badge) -> Badge:
        self._connection.execute(
            """
            INSERT INTO badges (account_id, name, image_path, owned, progress, is_event)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, name) DO UPDATE SET
                image_path = excluded.image_path,
                owned = excluded.owned,
                progress = excluded.progress,
                is_event = excluded.is_event
            """,
            (
                badge.account_id,
                badge.name,
                badge.image_path,
                badge.owned,
                badge.progress,
                badge.is_event,
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM badges WHERE account_id = ? AND name = ?",
            (badge.account_id, badge.name),
        ).fetchone()
        badge.id = row["id"]
        return badge

    def list_badges(self, account_id: int, owned_only: bool = False) -> list[Badge]:
        query = "SELECT * FROM badges WHERE account_id = ?"
        params: list = [account_id]
        if owned_only:
            query += " AND owned = 1"
        rows = self._connection.execute(query, params).fetchall()
        return [self._row_to_badge(row) for row in rows]

    @staticmethod
    def _row_to_stats(row: sqlite3.Row) -> ProfileStats:
        return ProfileStats(
            account_id=row["account_id"],
            points=row["points"],
            hardcore_points=row["hardcore_points"],
            games_beaten=row["games_beaten"],
            games_mastered=row["games_mastered"],
            completion_percentage=row["completion_percentage"],
            last_synced_at=datetime_from_sql(row["last_synced_at"]),
        )

    @staticmethod
    def _row_to_badge(row: sqlite3.Row) -> Badge:
        return Badge(
            id=row["id"],
            account_id=row["account_id"],
            name=row["name"],
            owned=bool(row["owned"]),
            image_path=row["image_path"],
            progress=row["progress"],
            is_event=bool(row["is_event"]),
        )
