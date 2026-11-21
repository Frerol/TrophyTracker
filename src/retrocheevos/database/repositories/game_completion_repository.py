"""Data access for the `game_completion` table (models/game_completion.py)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.game_completion import GameCompletion


class GameCompletionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, completion: GameCompletion) -> None:
        self._connection.execute(
            """
            INSERT INTO game_completion (
                account_id, game_id, percent_complete, highest_award_kind,
                achievements_unlocked, achievements_total, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, game_id) DO UPDATE SET
                percent_complete = excluded.percent_complete,
                highest_award_kind = COALESCE(
                    excluded.highest_award_kind, game_completion.highest_award_kind
                ),
                achievements_unlocked = COALESCE(
                    excluded.achievements_unlocked, game_completion.achievements_unlocked
                ),
                achievements_total = COALESCE(
                    excluded.achievements_total, game_completion.achievements_total
                ),
                last_synced_at = excluded.last_synced_at
            """,
            (
                completion.account_id,
                completion.game_id,
                completion.percent_complete,
                completion.highest_award_kind,
                completion.achievements_unlocked,
                completion.achievements_total,
                datetime_to_sql(completion.last_synced_at),
            ),
        )

    def get(self, account_id: int, game_id: int) -> Optional[GameCompletion]:
        row = self._connection.execute(
            "SELECT * FROM game_completion WHERE account_id = ? AND game_id = ?",
            (account_id, game_id),
        ).fetchone()
        return self._row_to_completion(row) if row else None

    def get_all_for_account(self, account_id: int) -> dict[int, float]:
        """game_id -> percent_complete, ready for the Explorer to merge into Game Cards."""
        rows = self._connection.execute(
            "SELECT game_id, percent_complete FROM game_completion WHERE account_id = ?",
            (account_id,),
        ).fetchall()
        return {row["game_id"]: row["percent_complete"] for row in rows}

    def get_achievement_counts_for_account(
        self, account_id: int
    ) -> dict[int, tuple[int, int]]:
        """game_id -> (unlocked, total), for the rows that carry raw counts —
        currently events (`sync_service.sync_event_progress`). Games whose
        progress only ever arrived as a percentage are absent rather than
        reported as 0/0.
        """
        rows = self._connection.execute(
            "SELECT game_id, achievements_unlocked, achievements_total "
            "FROM game_completion WHERE account_id = ? AND achievements_total IS NOT NULL",
            (account_id,),
        ).fetchall()
        return {
            row["game_id"]: (row["achievements_unlocked"] or 0, row["achievements_total"])
            for row in rows
        }

    def get_finished_game_ids(self, account_id: int) -> set[int]:
        """Game IDs this account is done with — beaten, completed or mastered
        — powering Explorer's "don't suggest what I've finished" exclusion.

        Single source of truth on purpose. Mastery used to be checked
        separately via `AchievementRepository.get_mastered_game_ids`, which
        reads `achievements`/`user_achievements` — tables nothing in the app
        ever populates, so that check silently matched nothing and mastered
        games kept showing up in search. RA's own per-game classification
        (`highest_award_kind`, from `API_GetUserCompletionProgress.php`) is
        the one that's actually filled in, so all four kinds are read from it.
        """
        rows = self._connection.execute(
            "SELECT game_id FROM game_completion WHERE account_id = ? "
            "AND highest_award_kind IN "
            "('beaten-hardcore', 'beaten-softcore', 'completed', 'mastered')",
            (account_id,),
        ).fetchall()
        return {row["game_id"] for row in rows}

    def get_mastered_game_ids(self, account_id: int) -> set[int]:
        """Games RA classifies as mastered for this account (Library's
        Mastered filter, ScreenDataMapping §3.2)."""
        rows = self._connection.execute(
            "SELECT game_id FROM game_completion WHERE account_id = ? "
            "AND highest_award_kind = 'mastered'",
            (account_id,),
        ).fetchall()
        return {row["game_id"] for row in rows}

    def get_fully_completed_game_ids(self, account_id: int) -> set[int]:
        """Games at 100%, regardless of award classification — a safety net
        for the window between finishing a game and RA's award data catching
        up in the next profile sync.
        """
        rows = self._connection.execute(
            "SELECT game_id FROM game_completion WHERE account_id = ? "
            "AND percent_complete >= 100",
            (account_id,),
        ).fetchall()
        return {row["game_id"] for row in rows}

    @staticmethod
    def _row_to_completion(row: sqlite3.Row) -> GameCompletion:
        return GameCompletion(
            account_id=row["account_id"],
            game_id=row["game_id"],
            percent_complete=row["percent_complete"],
            highest_award_kind=row["highest_award_kind"],
            achievements_unlocked=row["achievements_unlocked"],
            achievements_total=row["achievements_total"],
            last_synced_at=datetime_from_sql(row["last_synced_at"]),
        )
