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
