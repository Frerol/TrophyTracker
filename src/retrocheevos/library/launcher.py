"""Emulator process launching (Architecture.md — Library layer).

Pure mechanics only: given an executable, a ROM path, and an optional
argument template, build argv and start the process. No database lookups —
that's `services/library_service.py`'s job (Architecture.md's layering).
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROM_PATH_PLACEHOLDER = "{rom_path}"
# RetroArch and other libretro frontends take the core as `-L <path>`.
LIBRETRO_CORE_FLAG = "-L"


def build_launch_args(rom_path: Path, arguments_template: Optional[str]) -> list[str]:
    """Build the argv for launching an emulator with `rom_path`.

    - No template: args are just `[rom_path]`.
    - Template contains `{rom_path}`: the template is split into tokens
      *before* substitution, then the placeholder token is replaced with the
      full path as a single argv element — so spaces in the ROM path (common
      on Windows) don't get split apart.
    - Template without the placeholder: the path is appended as the last
      argument (forgiving default for simple emulators).
    """
    if not arguments_template:
        return [str(rom_path)]

    tokens = arguments_template.split()
    if ROM_PATH_PLACEHOLDER not in arguments_template:
        return [*tokens, str(rom_path)]

    return [
        token.replace(ROM_PATH_PLACEHOLDER, str(rom_path)) if ROM_PATH_PLACEHOLDER in token else token
        for token in tokens
    ]


def build_libretro_args(rom_path: Path, core_path: Path) -> list[str]:
    """argv for a libretro frontend: `-L <core> <rom>`.

    RetroArch doesn't have one executable per console — it has one binary and
    a `.dll`/`.so` core per emulated system, selected with `-L`. Each element
    stays a separate argv entry, so spaces in either path survive without
    quoting (the whole reason `build_launch_args` splits before substituting).
    """
    return [LIBRETRO_CORE_FLAG, str(core_path), str(rom_path)]


def launch_emulator(
    executable_path: Path,
    rom_path: Path,
    arguments_template: Optional[str] = None,
    core_path: Optional[Path] = None,
) -> subprocess.Popen:
    """Start the emulator as an independent process. Returns immediately (non-blocking).

    A `core_path` switches to the libretro form and **takes precedence over
    `arguments_template`**: the two describe the same thing, and a config
    carrying both is far more likely to be a leftover template from before
    the core was set than a deliberate combination.
    """
    if core_path is not None:
        args = build_libretro_args(rom_path, core_path)
    else:
        args = build_launch_args(rom_path, arguments_template)
    logger.info("Launching emulator: %s %s", executable_path, args)
    try:
        return subprocess.Popen([str(executable_path), *args])
    except OSError:
        logger.exception("Failed to launch emulator %s", executable_path)
        raise
