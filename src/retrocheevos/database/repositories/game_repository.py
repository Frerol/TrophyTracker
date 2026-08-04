"""Data access for `games` and `game_hashes` (Database.md 2.3, 2.4)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.game import Game, GameHash
from retrocheevos.utils.enums import GameType


class GameRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_game(self, game: Game) -> None:
        """Insert or update a game. Ids come from RetroAchievements, never autoincrement."""
        self._connection.execute(
            """
            INSERT INTO games (
                id, title, console_id, image_path, genre, game_type,
                has_achievements, median_time_to_beat_hardcore_seconds,
                times_used_in_hardcore_beat_median, retroachievements_url, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                console_id = excluded.console_id,
                image_path = excluded.image_path,
                genre = excluded.genre,
                game_type = excluded.game_type,
                has_achievements = excluded.has_achievements,
                median_time_to_beat_hardcore_seconds = excluded.median_time_to_beat_hardcore_seconds,
                times_used_in_hardcore_beat_median = excluded.times_used_in_hardcore_beat_median,
                retroachievements_url = excluded.retroachievements_url,
                last_synced_at = excluded.last_synced_at
            """,
            (
                game.id,
                game.title,
                game.console_id,
                game.image_path,
                game.genre,
                game.game_type.value if game.game_type else None,
                game.has_achievements,
                game.median_time_to_beat_hardcore_seconds,
                game.times_used_in_hardcore_beat_median,
                game.retroachievements_url,
                datetime_to_sql(game.last_synced_at),
            ),
        )

    def get_by_id(self, game_id: int) -> Optional[Game]:
        row = self._connection.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        return self._row_to_game(row) if row else None

    def count_all(self) -> int:
        """Total synced games, unfiltered — powers the Explorer "X of Y games" counter."""
        return self._connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    def search(
        self,
        text: Optional[str] = None,
        console_ids: Optional[list[int]] = None,
        game_types: Optional[list[GameType]] = None,
        has_achievements: Optional[bool] = None,
    ) -> list[Game]:
        """Cache-only search/filter backing the Explorer (UI.md 3.2). Never hits the network.

        List-membership and installed-status filters are layered on top by Core,
        which combines this with ListRepository/LibraryRepository results.
        """
        clauses: list[str] = []
        params: list = []

        if text:
            clauses.append("title LIKE ?")
            params.append(f"%{text}%")
        if console_ids:
            placeholders = ",".join("?" for _ in console_ids)
            clauses.append(f"console_id IN ({placeholders})")
            params.extend(console_ids)
        if game_types:
            placeholders = ",".join("?" for _ in game_types)
            clauses.append(f"game_type IN ({placeholders})")
            params.extend(game_type.value for game_type in game_types)
        if has_achievements is not None:
            clauses.append("has_achievements = ?")
            params.append(has_achievements)

        query = "SELECT * FROM games"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY title"

        rows = self._connection.execute(query, params).fetchall()
        return [self._row_to_game(row) for row in rows]

    def add_hash(self, game_hash: GameHash) -> None:
        self._connection.execute(
            "INSERT INTO game_hashes (game_id, hash) VALUES (?, ?)",
            (game_hash.game_id, game_hash.hash),
        )

    def get_hashes_for_game(self, game_id: int) -> list[str]:
        rows = self._connection.execute(
            "SELECT hash FROM game_hashes WHERE game_id = ?", (game_id,)
        ).fetchall()
        return [row["hash"] for row in rows]

    def find_game_id_by_hash(self, rom_hash: str) -> Optional[int]:
        """Look up the game a ROM hash matches. Never assume compatibility without a hit."""
        row = self._connection.execute(
            "SELECT game_id FROM game_hashes WHERE hash = ?", (rom_hash,)
        ).fetchone()
        return row["game_id"] if row else None

    @staticmethod
    def _row_to_game(row: sqlite3.Row) -> Game:
        return Game(
            id=row["id"],
            title=row["title"],
            console_id=row["console_id"],
            has_achievements=bool(row["has_achievements"]),
            image_path=row["image_path"],
            genre=row["genre"],
            game_type=GameType(row["game_type"]) if row["game_type"] else None,
            median_time_to_beat_hardcore_seconds=row["median_time_to_beat_hardcore_seconds"],
            times_used_in_hardcore_beat_median=row["times_used_in_hardcore_beat_median"],
            retroachievements_url=row["retroachievements_url"],
            last_synced_at=datetime_from_sql(row["last_synced_at"]),
        )
