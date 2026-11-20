"""Discover installed Flatpak emulators without starting or downloading apps."""

import logging
import shutil
import subprocess
import sys
import time
from typing import Callable, Optional

from retrocheevos.library.emulator_discovery import EMULATORS, _matching_emulator
from retrocheevos.library.process_environment import host_process_environment
from retrocheevos.models.emulator_discovery import EmulatorCandidate, EmulatorSearchResult

logger = logging.getLogger(__name__)
LIST_TIMEOUT_SECONDS = 5.0
POLL_SECONDS = 0.1

# IDs from Flathub's corresponding application manifests. For other installed
# apps, the final ID component must match a known emulator executable name.
FLATPAK_EMULATORS = {
    'org.libretro.RetroArch': 'RetroArch',
    'org.DolphinEmu.dolphin-emu': 'Dolphin',
    'org.ppsspp.PPSSPP': 'PPSSPP',
    'net.pcsx2.PCSX2': 'PCSX2',
    'org.duckstation.DuckStation': 'DuckStation',
    'io.mgba.mGBA': 'mGBA',
}


def discover_flatpaks(
    console_id: int,
    stop_requested: Optional[Callable[[], bool]] = None,
    result_callback: Optional[Callable[[EmulatorCandidate], None]] = None,
) -> EmulatorSearchResult:
    result = EmulatorSearchResult()
    if not sys.platform.startswith('linux'):
        return result
    if stop_requested is not None and stop_requested():
        result.cancelled = True
        return result
    executable = shutil.which('flatpak')
    if executable is None:
        return result
    definitions = tuple(item for item in EMULATORS if console_id in item.consoles)
    if not definitions:
        return result
    try:
        with subprocess.Popen(
            [executable, 'list', '--app', '--columns=application,installation'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=host_process_environment(),
        ) as process:
            deadline = time.monotonic() + LIST_TIMEOUT_SECONDS
            while True:
                if stop_requested is not None and stop_requested():
                    process.kill()
                    process.communicate()
                    result.cancelled = True
                    return result
                if time.monotonic() >= deadline:
                    process.kill()
                    process.communicate()
                    result.limited = True
                    result.warnings.append('Flatpak search timed out.')
                    return result
                try:
                    output, error = process.communicate(timeout=POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode != 0:
                logger.warning('Flatpak list failed: %s', error.strip())
                result.warnings.append('Could not read installed Flatpak applications.')
                return result
    except OSError as error:
        logger.warning('Could not query Flatpak applications: %s', error)
        result.warnings.append('Could not read installed Flatpak applications.')
        return result

    seen: set[tuple[str, str]] = set()
    for row in output.splitlines():
        if stop_requested is not None and stop_requested():
            result.cancelled = True
            break
        fields = row.split('\t')
        if len(fields) != 2:
            continue
        app_id, installation = (field.strip() for field in fields)
        if not app_id or not installation or (app_id, installation) in seen:
            continue
        name = FLATPAK_EMULATORS.get(app_id)
        definition = next((item for item in definitions if item.name == name), None)
        if name is None:
            definition = _matching_emulator(app_id.rsplit('.', 1)[-1], definitions)
        if definition is None:
            continue
        seen.add((app_id, installation))
        candidate = EmulatorCandidate(
            definition.name, executable, definition.requires_core,
            flatpak_app_id=app_id, flatpak_installation=installation,
        )
        result.candidates.append(candidate)
        if result_callback is not None:
            result_callback(candidate)
    logger.info('Flatpak emulator search: console=%s, found=%d', console_id, len(result.candidates))
    return result
