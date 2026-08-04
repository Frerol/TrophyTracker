"""Shared enums used across layers to avoid magic values."""

from enum import Enum


class GameType(str, Enum):
    RETAIL = "Retail"
    HOMEBREW = "Homebrew"
    HACK = "Hack"
    DEMO = "Demo"
    PROTOTYPE = "Prototype"


class ListType(str, Enum):
    WANT_TO_PLAY = "want_to_play"
    PLAYING = "playing"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    FOLLOWING = "following"
    BLOCKED = "blocked"


class NotificationType(str, Enum):
    ACHIEVEMENT_RELEASED = "achievement_released"
    NEW_SUPPORTED_GAME = "new_supported_game"
    BADGE = "badge"
    EVENT = "event"
    FOLLOWED_GAME_UPDATE = "followed_game_update"


class LeaderboardScope(str, Enum):
    FRIENDS = "friends"
    DAILY = "daily"
    WEEKLY = "weekly"
    ALL_TIME = "all_time"
    GAMES_BEATEN = "games_beaten"
