"""Library grid filters (R22, ScreenDataMapping §3.2) — pure functions.

Statuses: All; In progress (some progress and not mastered — games with no
completion record are excluded, never treated as 0%); Mastered; Unmatched
(installed ROMs with no catalog match, D9).
"""

from typing import Iterable, Optional

from retrocheevos.models.library import LibraryEntry

STATUS_ALL = "all"
STATUS_IN_PROGRESS = "in_progress"
STATUS_MASTERED = "mastered"
STATUS_UNMATCHED = "unmatched"
STATUSES = (STATUS_ALL, STATUS_IN_PROGRESS, STATUS_MASTERED, STATUS_UNMATCHED)


def _in_progress(entry: LibraryEntry) -> bool:
    if entry.kind != "game" or entry.mastered:
        return False
    if entry.achievements_unlocked is not None and entry.achievements_total:
        return 0 < entry.achievements_unlocked < entry.achievements_total
    return entry.percent_complete is not None and 0 < entry.percent_complete < 100


def matches_status(entry: LibraryEntry, status: str) -> bool:
    if status == STATUS_IN_PROGRESS:
        return _in_progress(entry)
    if status == STATUS_MASTERED:
        return entry.kind == "game" and entry.mastered
    if status == STATUS_UNMATCHED:
        return entry.kind == "rom"
    return True


def matches_text(entry: LibraryEntry, text: str) -> bool:
    needle = text.strip().casefold()
    if not needle:
        return True
    if needle in entry.title.casefold():
        return True
    return any(needle in path.replace("\\", "/").rsplit("/", 1)[-1].casefold()
               for path in entry.file_paths)


def filter_entries(
    entries: Iterable[LibraryEntry],
    status: str = STATUS_ALL,
    console_id: Optional[int] = None,
    text: str = "",
) -> list[LibraryEntry]:
    return [
        entry for entry in entries
        if matches_status(entry, status)
        and (console_id is None or entry.console_id == console_id)
        and matches_text(entry, text)
    ]
