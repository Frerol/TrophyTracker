"""Local emulator discovery for Settings; runs on a background worker."""

from pathlib import Path
from typing import Callable, Optional

from retrocheevos.library.emulator_discovery import common_search_roots, discover_emulators
from retrocheevos.library.flatpak import discover_flatpaks
from retrocheevos.models.emulator_discovery import EmulatorCandidate, EmulatorSearchResult


def find_emulators(
    console_id: int,
    folder: Optional[str] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
    result_callback: Optional[Callable[[EmulatorCandidate], None]] = None,
) -> EmulatorSearchResult:
    roots = [Path(folder)] if folder else common_search_roots()
    # Query installed apps first so they appear before the longer disk scan.
    result = (
        discover_flatpaks(console_id, stop_requested, result_callback)
        if folder is None else EmulatorSearchResult()
    )
    if result.cancelled:
        return result
    local = discover_emulators(console_id, roots, stop_requested, result_callback)
    result.candidates.extend(local.candidates)
    result.cancelled = local.cancelled
    result.limited = result.limited or local.limited
    result.warnings.extend(local.warnings)
    return result
