"""Moves ROM files into their console's configured destination folder
(Architecture.md — Library layer, "console-folder organizer"). Used by Watch
Folder scanning (`services/library_service.py`) to turn a confirmed console
match into an actual file move, never guessed — the caller already decided
the console *and* already knows its destination folder (Settings > ROM
Destinations, `rom_destinations` table); this module has no opinion on
where that folder should be.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_destination(destination_folder: Path, file_path: Path) -> Path:
    """Where `file_path` should live: `<destination_folder>/<original filename>`.

    If a *different* file already occupies that path, appends " (2)", " (3)",
    etc. to the filename stem rather than overwriting it.
    """
    destination = destination_folder / file_path.name

    suffix = 1
    while destination.exists() and not destination.samefile(file_path):
        suffix += 1
        destination = destination_folder / f"{file_path.stem} ({suffix}){file_path.suffix}"

    return destination


def move_rom(file_path: Path, destination: Path) -> Path:
    """Moves `file_path` to `destination`, creating the destination folder
    if needed. No-op if the file is already there.
    """
    if destination.resolve() == file_path.resolve():
        return file_path

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), str(destination))
    logger.info("Moved %s -> %s", file_path, destination)
    return destination
