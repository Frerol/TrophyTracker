"""Data access for `games` and `game_hashes` (Database.md 2.3, 2.4)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.game import Game, GameHash
from retrocheevos.utils.enums import GameType

# RetroAchievements models community events as "games" on their own console,
# and ships achievement subsets ("Sonic [Subset - Bonus]") as separate
# entries alongside the base game. Neither is a game you'd go looking for in
# a catalog browser: events have their own Home section
# (`services/events_service.py`), and a subset is extra achievements for a
# title that is already listed. Excluding all three brings the catalog count
# to ~11.3k, matching what retroachievements.org itself reports; counting
# them inflated it to ~12k.
EVENTS_CONSOLE_ID = 101
STANDALONE_CONSOLE_ID = 102
_BROWSABLE_GAME_CLAUSES = [
    "has_achievements = 1",
    f"console_id NOT IN ({EVENTS_CONSOLE_ID}, {STANDALONE_CONSOLE_ID})",
    "title NOT LIKE '%[Subset%'",
]


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
                -- COALESCE, not a plain overwrite: the bulk catalog sync
                -- (`API_GetGameList.php`) doesn't return median time and
                -- passes NULL, which would otherwise wipe values that
                -- `sync_median_times_for_console` spent an API call each to
                -- fetch. Only a real incoming value replaces a stored one.
                median_time_to_beat_hardcore_seconds = COALESCE(
                    excluded.median_time_to_beat_hardcore_seconds,
                    games.median_time_to_beat_hardcore_seconds
                ),
                times_used_in_hardcore_beat_median = COALESCE(
                    excluded.times_used_in_hardcore_beat_median,
                    games.times_used_in_hardcore_beat_median
                ),
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

    def set_median_time(
        self, game_id: int, seconds: Optional[int], sample_size: Optional[int]
    ) -> None:
        """Writes just the median-time columns, for
        `sync_service.sync_median_times_for_console`'s per-game backfill —
        that data comes from a different endpoint than the rest of the row,
        so going through `upsert_game` would mean re-sending (and risking
        staleness in) every other field.
        """
        self._connection.execute(
            "UPDATE games SET median_time_to_beat_hardcore_seconds = ?, "
            "times_used_in_hardcore_beat_median = ? WHERE id = ?",
            (seconds, sample_size, game_id),
        )

    def list_ids_missing_median_time(self) -> list[int]:
        """Browsable games still needing a median-time fetch, most useful
        first — lets the backfill resume where it left off instead of
        re-requesting everything after an interruption.

        Ordered by relevance rather than by id, because the fetch is one
        API request per game and RetroAchievements' rate limiter caps that
        at roughly three per second — a full catalog takes about an hour no
        matter what. Ordering means the filter becomes useful for the games
        you actually own within seconds, instead of only after the whole
        run finishes:
          1. games with a ROM installed
          2. games on a console you have ROMs for
          3. everything else

        Scoped to the browsable catalog so the backfill doesn't spend
        requests on events/subsets the Explorer never shows anyway.
        """
        rows = self._connection.execute(
            "SELECT id FROM games WHERE "
            + " AND ".join(_BROWSABLE_GAME_CLAUSES)
            + """ AND median_time_to_beat_hardcore_seconds IS NULL
            ORDER BY
                CASE
                    WHEN id IN (
                        SELECT game_id FROM installed_roms WHERE game_id IS NOT NULL
                    ) THEN 0
                    WHEN console_id IN (SELECT DISTINCT console_id FROM installed_roms)
                        THEN 1
                    ELSE 2
                END,
                id
            """
        ).fetchall()
        return [row["id"] for row in rows]

    def get_by_id(self, game_id: int) -> Optional[Game]:
        row = self._connection.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        return self._row_to_game(row) if row else None

    def count_all(self) -> int:
        """Size of the browsable catalog — the "Y" in Explorer's "X of Y games".

        Shares `_BROWSABLE_GAME_CLAUSES` with `search()` on purpose: if the
        two disagreed, the total would count entries the list could never
        show.
        """
        return self._connection.execute(
            "SELECT COUNT(*) FROM games WHERE " + " AND ".join(_BROWSABLE_GAME_CLAUSES)
        ).fetchone()[0]

    def count_for_console(self, console_id: int) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM games WHERE console_id = ? AND has_achievements = 1",
            (console_id,),
        ).fetchone()[0]

    def list_console_ids_with_games(self) -> list[int]:
        """Consoles that have at least one browsable game — excludes both the
        ones never synced and the special Events/Standalone consoles.
        """
        rows = self._connection.execute(
            "SELECT DISTINCT console_id FROM games WHERE "
            + " AND ".join(_BROWSABLE_GAME_CLAUSES)
        ).fetchall()
        return [row["console_id"] for row in rows]

    def list_events(self) -> list[Game]:
        """Community events, which `search()`/`count_all()` deliberately
        exclude from the catalog — Home shows them in their own section
        (`services/events_service.py`), so they need a way in that isn't the
        browsable-catalog query.
        """
        rows = self._connection.execute(
            "SELECT * FROM games WHERE console_id = ? ORDER BY title",
            (EVENTS_CONSOLE_ID,),
        ).fetchall()
        return [self._row_to_game(row) for row in rows]

    def search(
        self,
        text: Optional[str] = None,
        console_ids: Optional[list[int]] = None,
        game_types: Optional[list[GameType]] = None,
    ) -> list[Game]:
        """Cache-only search/filter backing the Explorer (UI.md 3.2). Never hits the network.

        Always limited to the browsable catalog (see `_BROWSABLE_GAME_CLAUSES`).
        List-membership and installed-status filters are layered on top by Core,
        which combines this with ListRepository/LibraryRepository results.
        """
        clauses: list[str] = list(_BROWSABLE_GAME_CLAUSES)
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

        query = "SELECT * FROM games WHERE " + " AND ".join(clauses)
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
