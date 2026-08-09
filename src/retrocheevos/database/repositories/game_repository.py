"""Data access for `games` and `game_hashes` (Database.md 2.3, 2.4)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.game import Game
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

        Ordered by relevance rather than by id, because the fetch is one API
        request per game and the pacing plus the round trip works out at
        ~0.5s each (measured — see `sync_service.sync_all_game_hashes`), so a
        full catalog is ~1h40 no matter what. This ordering is what makes
        that bearable: the prefix covering consoles the user owns ROMs for
        was ~5k games, about 45 minutes, after which the run can be stopped
        with nothing relevant left undone. Without it the useful answers
        would arrive only when the whole run finished:
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

    def list_ids_missing_hashes(self) -> list[int]:
        """Browsable games with no ROM hash stored yet, ordered like
        `list_ids_missing_median_time` — installed first, then your consoles,
        then the rest.

        Resumability is the point. The hash backfill is one request per game
        across ~12k games; without a "what's still missing" query, an
        interruption means starting over, and at ~1h40 that is the difference
        between a job you can stop and one you cannot.

        A game that genuinely has no hashes on RetroAchievements comes back
        every time, since "fetched and empty" and "never fetched" look
        identical here. That costs a repeat request on a re-run and is worth
        it: the alternative is a `hashes_synced_at` column whose only job is
        remembering an empty answer.
        """
        rows = self._connection.execute(
            "SELECT id FROM games WHERE "
            + " AND ".join(_BROWSABLE_GAME_CLAUSES)
            + """ AND id NOT IN (SELECT DISTINCT game_id FROM game_hashes)
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

    def replace_hashes(self, game_id: int, hashes: list[str]) -> None:
        """Swap in this game's hash set, normalized to lowercase.

        `add_hash` alone would duplicate every row on a re-run — there is no
        unique constraint on `(game_id, hash)` — so a resumable backfill that
        revisits a game has to clear first.

        Lowercased on the way in because the API is inconsistent about case
        (see `find_game_id_by_hash`) and every hasher this app uses prints
        lowercase. Normalizing at the single point of entry keeps the lookup
        able to use its index in the common case; the `LOWER()` there is for
        rows that predate this.
        """
        self._connection.execute("DELETE FROM game_hashes WHERE game_id = ?", (game_id,))
        for rom_hash in hashes:
            self._connection.execute(
                "INSERT INTO game_hashes (game_id, hash) VALUES (?, ?)",
                (game_id, rom_hash.lower()),
            )

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

    def find_game_id_by_hash(self, rom_hash: str) -> Optional[int]:
        """Look up the game a ROM hash matches. Never assume compatibility without a hit.

        Compared case-insensitively, because RetroAchievements' API is not
        consistent about it: 176 of 13327 synced hashes came back uppercase
        (Pokémon Snap, Terranigma, Jet Force Gemini…) while the rest were
        lowercase, and RAHasher always prints lowercase. SQLite's `=` on TEXT
        is case-sensitive, so those 137 games could never be matched by any
        correctly-hashed ROM — Pokémon Snap sat in "Unmatched ROMs" with a
        hash that was character-for-character right apart from its case.

        `LOWER(hash)` on the left defeats `idx_game_hashes_hash`, so this is
        a scan of a table with a few tens of thousands of rows. `store_hashes`
        lowercases on the way in specifically so that stays the fallback path
        rather than the normal one; the function-side LOWER is what covers
        rows written before that existed.
        """
        row = self._connection.execute(
            "SELECT game_id FROM game_hashes WHERE LOWER(hash) = LOWER(?)", (rom_hash,)
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
