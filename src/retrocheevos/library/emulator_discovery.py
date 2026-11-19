"""Read-only discovery of known emulator executables; never runs candidates."""

import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from retrocheevos.models.emulator_discovery import EmulatorCandidate, EmulatorSearchResult

logger = logging.getLogger(__name__)
MAX_DIRECTORIES = 15000
MAX_DEPTH = 7
MAX_SEARCH_SECONDS = 30.0
SKIPPED_DIRECTORIES = frozenset({
    'node_modules', '__pycache__', '.git', '.venv', 'venv', 'cache', 'caches',
    'trash', '$recycle.bin', 'system volume information',
})


@dataclass(frozen=True)
class EmulatorDefinition:
    name: str
    filenames: tuple[str, ...]
    consoles: frozenset[int]
    requires_core: bool = False


EMULATORS = (
    EmulatorDefinition('RetroArch', ('retroarch',), frozenset({
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
        19, 21, 23, 24, 25, 26, 27, 28, 29, 30, 33, 35, 37, 38, 39, 40, 41,
        43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57,
        58, 59, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 72, 73, 74, 76, 77, 81,
    }), True),
    EmulatorDefinition('DuckStation', ('duckstation', 'duckstation-qt'), frozenset({12})),
    EmulatorDefinition('PCSX2', ('pcsx2', 'pcsx2-qt'), frozenset({21})),
    EmulatorDefinition(
        'PPSSPP', ('ppsspp', 'ppssppqt', 'ppssppsdl', 'ppssppwindows', 'ppssppwindows64'),
        frozenset({41}),
    ),
    EmulatorDefinition('Dolphin', ('dolphin-emu', 'dolphin_emulator', 'dolphin'), frozenset({16, 19})),
    EmulatorDefinition('mGBA', ('mgba', 'mgba-qt'), frozenset({4, 5, 6})),
    EmulatorDefinition('melonDS', ('melonds',), frozenset({18, 78})),
    EmulatorDefinition('DeSmuME', ('desmume', 'desmume-gtk', 'desmume-cli'), frozenset({18})),
    EmulatorDefinition('Snes9x', ('snes9x', 'snes9x-gtk', 'snes9x-x64'), frozenset({3})),
    EmulatorDefinition('bsnes', ('bsnes',), frozenset({3})),
    EmulatorDefinition('Mesen', ('mesen',), frozenset({3, 4, 6, 7, 8, 76, 81})),
    EmulatorDefinition('FCEUX', ('fceux',), frozenset({7, 81})),
    EmulatorDefinition('Project64', ('project64',), frozenset({2})),
    EmulatorDefinition('RMG', ('rmg',), frozenset({2})),
    EmulatorDefinition('simple64', ('simple64-gui', 'simple64'), frozenset({2})),
    EmulatorDefinition('Mupen64Plus', ('mupen64plus',), frozenset({2})),
    EmulatorDefinition('Flycast', ('flycast',), frozenset({40, 27})),
    EmulatorDefinition('MAME', ('mame', 'mame64'), frozenset({27})),
    EmulatorDefinition(
        'Mednafen', ('mednafen',),
        frozenset({1, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 28, 39, 49, 53, 76, 81}),
    ),
    EmulatorDefinition('RPCS3', ('rpcs3',), frozenset({82})),
    EmulatorDefinition('Cemu', ('cemu',), frozenset({20})),
    EmulatorDefinition('Azahar', ('azahar',), frozenset({62})),
    EmulatorDefinition('DOSBox', ('dosbox', 'dosbox-x', 'dosbox-staging'), frozenset({26})),
)


def common_search_roots() -> list[Path]:
    """PATH plus common system, user, and portable-app installation locations."""
    home = Path.home()
    roots = [Path(value) for value in os.get_exec_path() if value]
    roots.extend(home / name for name in (
        'Applications', 'Emulators', 'Games', 'Downloads', 'Desktop',
        'Aplicativos', 'Emuladores', 'Jogos', 'Transferências', 'Área de Trabalho',
    ))
    if sys.platform == 'win32':
        for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            if os.environ.get(key):
                roots.append(Path(os.environ[key]))
    elif sys.platform == 'darwin':
        roots.append(Path('/Applications'))
    else:
        roots.extend((Path('/opt'), home / '.local/bin', home / '.local/opt', home / 'AppImages'))
    return roots


def _matching_emulator(
    filename: str, definitions: tuple[EmulatorDefinition, ...]
) -> Optional[EmulatorDefinition]:
    name = filename.casefold()
    if re.search(r'(?:^|[-_])(setup|installer|uninstall|updater)(?:[-_.]|$)', name):
        return None
    if sys.platform == 'win32':
        if not name.endswith('.exe'):
            return None
        name = name[:-4]
    elif name.endswith('.appimage'):
        name = name[:-9]
    elif name.endswith(('.exe', '.dll', '.so', '.zip', '.7z', '.tar', '.gz')):
        return None
    elif '.' in name and not re.search(r'[-_]v?\d', name):
        return None
    for definition in definitions:
        for alias in definition.filenames:
            # On Linux, "dolphin" is KDE's file manager. The emulator is
            # packaged as dolphin-emu; Dolphin.exe is valid on Windows.
            if alias == 'dolphin' and sys.platform not in ('win32', 'darwin'):
                continue
            # Allow versioned/architecture-specific portable builds, but not
            # similarly named installers, DLLs, updaters, or ROM files.
            if re.fullmatch(re.escape(alias) + r'(?:[-_](?:v?\d|linux|x64|x86|aarch|arm|qt).*)?', name):
                return definition
    return None


def discover_emulators(
    console_id: int,
    roots: list[Path],
    stop_requested: Optional[Callable[[], bool]] = None,
    result_callback: Optional[Callable[[EmulatorCandidate], None]] = None,
) -> EmulatorSearchResult:
    """Bounded, cancellable traversal. Skip directory symlinks and unreadable paths."""
    result = EmulatorSearchResult()
    definitions = tuple(emulator for emulator in EMULATORS if console_id in emulator.consoles)
    if not definitions:
        return result
    visited: set[str] = set()
    found: set[str] = set()
    started = time.monotonic()
    pending = [(root, 0) for root in reversed(roots)]

    def should_stop() -> bool:
        if stop_requested is not None and stop_requested():
            result.cancelled = True
            return True
        if len(visited) >= MAX_DIRECTORIES or time.monotonic() - started >= MAX_SEARCH_SECONDS:
            result.limited = True
            return True
        return False

    while pending:
        if should_stop():
            break
        directory, depth = pending.pop()
        try:
            key = os.path.normcase(str(directory.resolve()))
            if key in visited:
                continue
            visited.add(key)
            with os.scandir(directory) as entries:
                for entry in entries:
                    if should_stop():
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if (
                                depth < MAX_DEPTH
                                and not entry.name.startswith('.')
                                and entry.name.casefold() not in SKIPPED_DIRECTORIES
                            ):
                                pending.append((Path(entry.path), depth + 1))
                            continue
                        definition = _matching_emulator(entry.name, definitions)
                        if definition is None or not entry.is_file():
                            continue
                        if sys.platform != 'win32' and not os.access(entry.path, os.X_OK):
                            continue
                        # Deduplicate symlinks but retain the launch path/name:
                        # argv[0] can matter for packaged launch wrappers.
                        target = os.path.normcase(str(Path(entry.path).resolve()))
                        if target in found:
                            continue
                        found.add(target)
                        candidate = EmulatorCandidate(
                            definition.name, str(Path(entry.path).absolute()), definition.requires_core
                        )
                        result.candidates.append(candidate)
                        if result_callback is not None:
                            result_callback(candidate)
                    except OSError as error:
                        logger.debug('Skipping emulator candidate %s: %s', entry.path, error)
        except (OSError, RuntimeError) as error:
            logger.debug('Cannot search emulator directory %s: %s', directory, error)
    result.candidates.sort(key=lambda candidate: (candidate.name.casefold(), candidate.executable_path.casefold()))
    logger.info(
        'Emulator search: console=%s, found=%d, cancelled=%s, limited=%s',
        console_id, len(result.candidates), result.cancelled, result.limited,
    )
    return result
