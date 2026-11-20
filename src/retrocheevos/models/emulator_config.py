"""EmulatorConfig DTO — per-console emulator executable + launch arguments.

Not part of the original Database.md schema — added (migration v4) to power
the "Play" button on the Game Card and Library page.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EmulatorConfig:
    console_id: int
    executable_path: str
    arguments_template: Optional[str] = None
    # libretro core (`.dll`/`.so`) for frontends like RetroArch, which have
    # one binary and a core per emulated system rather than an executable
    # per console. Set ⇒ launch as `retroarch.exe -L <core> <rom>` and
    # `arguments_template` is ignored (migration v19).
    core_path: Optional[str] = None
    flatpak_app_id: Optional[str] = None
    flatpak_installation: Optional[str] = None
