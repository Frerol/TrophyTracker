"""Game, achievement-definition, and ROM-hash lookups (API.md §3).

Returns raw, API-shaped data structures (Architecture.md §2.1) — mapping
these into `models/` domain DTOs (e.g. resolving `game_type_flags` into a
`utils.enums.GameType`) is a `core/` responsibility, not this layer's.
"""

from dataclasses import dataclass
from typing import Optional

from retrocheevos.api.client import RetroAchievementsClient


@dataclass
class RawConsole:
    id: int
    name: str


@dataclass
class RawGame:
    id: int
    title: str
    console_id: int
    image_icon_path: Optional[str]
    num_achievements: int


@dataclass
class RawAchievementDefinition:
    id: int
    game_id: int
    title: str
    description: str
    points: int
    badge_name: Optional[str]


@dataclass
class RawGameProgression:
    game_id: int
    median_time_to_beat_hardcore_seconds: Optional[int]
    times_used_in_hardcore_beat_median: Optional[int]


@dataclass
class RawUserGameProgress:
    game_id: int
    title: str
    console_name: Optional[str]
    achievements_unlocked: int
    achievements_total: int
    playtime_seconds: Optional[int]


class GamesClient:
    def __init__(self, client: RetroAchievementsClient) -> None:
        self._client = client

    def list_console_ids(self) -> list[RawConsole]:
        payload = self._client.get("API_GetConsoleIDs.php")
        return [RawConsole(id=item["ID"], name=item["Name"]) for item in payload]

    def list_games_for_console(
        self, console_id: int, only_with_achievements: bool = False
    ) -> list[RawGame]:
        params: dict = {"i": console_id}
        if only_with_achievements:
            params["f"] = 1
        payload = self._client.get("API_GetGameList.php", params)
        return [
            RawGame(
                id=item["ID"],
                title=item["Title"],
                console_id=console_id,
                image_icon_path=item.get("ImageIcon"),
                num_achievements=item.get("NumAchievements", 0),
            )
            for item in payload
        ]

    def list_games_with_hashes(self, console_id: int) -> list[tuple[RawGame, list[str]]]:
        """Every game with achievements on a console, with its supported ROM
        hashes, in one request (`h=1`). Far cheaper than `get_game_hashes`
        per game when a whole console's hashes are needed (R22)."""
        payload = self._client.get("API_GetGameList.php", {"i": console_id, "f": 1, "h": 1})
        return [
            (
                RawGame(
                    id=item["ID"],
                    title=item["Title"],
                    console_id=console_id,
                    image_icon_path=item.get("ImageIcon"),
                    num_achievements=item.get("NumAchievements", 0),
                ),
                [str(value) for value in (item.get("Hashes") or []) if value],
            )
            for item in payload
        ]

    def get_game_extended(self, game_id: int) -> tuple[RawGame, list[RawAchievementDefinition]]:
        """Fetch a game's metadata plus its full achievement list in one call."""
        payload = self._client.get("API_GetGameExtended.php", {"i": game_id})
        raw_achievements = payload.get("Achievements", {})

        game = RawGame(
            id=payload["ID"],
            title=payload["Title"],
            console_id=payload["ConsoleID"],
            image_icon_path=payload.get("ImageIcon"),
            num_achievements=len(raw_achievements),
        )
        achievements = [
            RawAchievementDefinition(
                id=int(achievement_id),
                game_id=game.id,
                title=data["Title"],
                description=data["Description"],
                points=data["Points"],
                badge_name=data.get("BadgeName"),
            )
            for achievement_id, data in raw_achievements.items()
        ]
        return game, achievements

    def get_game_hashes(self, game_id: int) -> list[str]:
        payload = self._client.get("API_GetGameHashes.php", {"i": game_id})
        return [entry["MD5"] for entry in payload.get("Results", [])]

    def get_median_time_to_beat_hardcore(self, game_id: int) -> RawGameProgression:
        """Fetch the hardcore median time-to-beat for a game.

        RetroAchievements' own field is a *median*, not an average — despite
        this project's docs originally saying "Average Time", the underlying
        stat is `MedianTimeToBeatHardcore`. Field and method names here (and
        in `models/`/the UI) say "median" on purpose, to not misrepresent the
        data (confirmed against the real endpoint, not scraped — Architecture.md §6).
        """
        payload = self._client.get("API_GetGameProgression.php", {"i": game_id, "h": 1})
        return RawGameProgression(
            game_id=game_id,
            median_time_to_beat_hardcore_seconds=payload.get("MedianTimeToBeatHardcore"),
            times_used_in_hardcore_beat_median=payload.get("TimesUsedInHardcoreBeatMedian"),
        )

    def get_user_game_progress(self, username: str, game_id: int) -> RawUserGameProgress:
        """Confirmed live (Recent Activity redesign, docs/archive/RoadmapHistory.md):
        works for `u=<any username>`, not just the authenticated account.
        `UserTotalPlaytime` is in seconds.
        """
        payload = self._client.get(
            "API_GetGameInfoAndUserProgress.php", {"u": username, "g": game_id}
        )
        return RawUserGameProgress(
            game_id=game_id,
            title=payload.get("Title", ""),
            console_name=payload.get("ConsoleName"),
            achievements_unlocked=payload.get("NumAwardedToUser", 0),
            achievements_total=payload.get("NumAchievements", 0),
            playtime_seconds=payload.get("UserTotalPlaytime"),
        )
