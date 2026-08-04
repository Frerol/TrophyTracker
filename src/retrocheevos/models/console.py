"""Console DTO — maps to the `consoles` table (Database.md 2.2)."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Console:
    id: int  # RetroAchievements console ID, externally assigned
    name: str
    icon_path: Optional[str] = None
