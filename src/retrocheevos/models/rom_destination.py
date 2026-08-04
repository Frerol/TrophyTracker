"""RomDestination DTO — per-console ROM organizing folder, user-chosen.

Not part of the original Database.md schema — added (migration v5) to power
Watch Folder organizing. Distinct from `EmulatorConfig`: that's the emulator
executable path, this is where ROMs for that console should be moved to.
"""

from dataclasses import dataclass


@dataclass
class RomDestination:
    console_id: int
    path: str
