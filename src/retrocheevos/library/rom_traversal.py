"""Streaming ROM-tree mechanics; exclusion policy is supplied by the caller."""

import os
from pathlib import Path
from typing import Callable, Collection, Iterator, Optional

from retrocheevos.utils.cancellation import raise_if_cancelled


def iter_rom_files(
    root: Path,
    skipped_directories: Collection[str],
    progress_callback: Optional[Callable[[int, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    on_error: Optional[Callable[[Path, OSError], None]] = None,
) -> Iterator[Path]:
    """Depth-first traversal with O(depth) open iterators and no tree-sized list.

    Directory symlinks are not followed, matching Path.rglob's behavior.
    Hidden directories are traversed: the existing policy only excludes
    hidden *files*, and named exclusions apply below the configured root.
    Progress includes directories and rejected entries, before any hashing.
    """
    visited = 0
    raise_if_cancelled(should_cancel)
    if progress_callback:
        progress_callback(visited, str(root))
    stack = []

    def report_error(path: Path, error: OSError) -> None:
        if on_error is None:
            raise error
        on_error(path, error)

    try:
        stack.append((root, os.scandir(root)))
        while stack:
            raise_if_cancelled(should_cancel)
            directory, iterator = stack[-1]
            try:
                entry = next(iterator)
            except StopIteration:
                iterator.close()
                stack.pop()
                continue
            except OSError as error:
                iterator.close()
                stack.pop()
                report_error(directory, error)
                continue
            path = Path(entry.path)
            visited += 1
            if progress_callback:
                progress_callback(visited, str(path))
            raise_if_cancelled(should_cancel)
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.casefold() not in skipped_directories:
                        stack.append((path, os.scandir(path)))
                elif entry.is_file():
                    yield path
            except OSError as error:
                report_error(path, error)
    finally:
        for _, iterator in stack:
            iterator.close()
