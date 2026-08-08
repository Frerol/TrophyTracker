"""Where this install is allowed to write.

One home for the frozen-vs-source path decision, because it was previously
made correctly in exactly one place (`database/connection.py`) and not at all
in the four image-cache modules, which each derived a directory from
`__file__` and wrote into it.

That difference is invisible from source — `__file__` really is inside the
repo there — and only bites in the .exe, where `__file__` points inside the
PyInstaller bundle. Three consequences, none of which announce themselves:

  - The cache lands next to the executable. Installed anywhere a normal user
    can't write (Program Files), every save fails silently.
  - In a one-file build, the bundle directory is temporary, so the cache is
    thrown away on exit and re-downloaded on every launch.
  - Worst of the three: it is per-*install*, not per-user. Two Windows users
    sharing one install would share a cache of downloaded profile pictures —
    one account's data sitting in a directory owned by the other. Data
    belongs to whoever is logged into the machine, not to the copy of the
    program.

Nothing here creates directories; callers do that when they write.
"""

import os
import sys
from pathlib import Path

APP_DIR_NAME = "Retrocheevos"

# `parents[1]` from `src/retrocheevos/paths.py` is `src/`; `parents[2]` is the
# repo root, which is what the source layout has always used.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """The per-user data directory when frozen; the repo root from source.

    Keeping the source path as the repo root means development is unchanged:
    `database/` and `logs/` stay exactly where they have always been.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / f".{APP_DIR_NAME.lower()}"
    return PROJECT_ROOT


def cache_dir(name: str) -> Path:
    """A named subdirectory of `<data dir>/cache` — e.g. `cache("images")`.

    Downloaded artwork and avatars, all of it re-fetchable. It sits under the
    same per-user root as the database rather than somewhere like %TEMP% so
    that deleting one person's Retrocheevos data is a single directory, with
    nothing of theirs left behind elsewhere.
    """
    return data_dir() / "cache" / name
