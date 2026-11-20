"""Shared enums used across layers to avoid magic values."""

from enum import Enum


class GameType(str, Enum):
    RETAIL = "Retail"
    HOMEBREW = "Homebrew"
    HACK = "Hack"
    DEMO = "Demo"
    PROTOTYPE = "Prototype"


class ListType(str, Enum):
    """The *predefined* lists — the ones code reasons about by identity.

    Since Bloco 12 a list is a row in `user_list_definitions`, not a value
    here, and the user can create lists with any name they like. Those carry
    no `ListType` at all (`slug IS NULL`): nothing branches on them. A member
    exists here only when some rule depends on it — `BLOCKED` hides games
    from Explorer, `LIBRARY` is resolved live from installed ROMs instead of
    stored rows. The rest are predefined purely so a fresh account starts
    with something useful.
    """

    WANT_TO_PLAY = "want_to_play"
    PLAYING = "playing"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"
    LIBRARY = "library"


class NotificationType(str, Enum):
    ACHIEVEMENT_RELEASED = "achievement_released"
    NEW_SUPPORTED_GAME = "new_supported_game"
    BADGE = "badge"
    EVENT = "event"
    FOLLOWED_GAME_UPDATE = "followed_game_update"


class MetadataKind(str, Enum):
    HASHES = "hashes"
    MEDIAN_TIME = "median_time"


class MetadataFetchOutcome(str, Enum):
    VALUE = "value"
    EMPTY = "empty"
    FAILED = "failed"
