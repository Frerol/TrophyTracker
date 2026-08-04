"""Game-type classification from RetroAchievements title conventions.

RetroAchievements marks non-retail games with a tilde-wrapped tag at the
start of the title (e.g. "~Hack~ Super Mario World: Kaizo"). This is a
community convention, not an explicit API field, so treat this as a
best-effort classifier — revisit if RA ever exposes a real "Type" field.
"""

import re

from retrocheevos.utils.enums import GameType

_TITLE_TAG_PATTERN = re.compile(r"^~(?P<tag>[^~]+)~")

_TAG_TO_GAME_TYPE = {
    "hack": GameType.HACK,
    "homebrew": GameType.HOMEBREW,
    "demo": GameType.DEMO,
    "prototype": GameType.PROTOTYPE,
}


def classify_game_type(title: str) -> GameType:
    match = _TITLE_TAG_PATTERN.match(title.strip())
    if match:
        tag = match.group("tag").strip().lower()
        if tag in _TAG_TO_GAME_TYPE:
            return _TAG_TO_GAME_TYPE[tag]
    return GameType.RETAIL
