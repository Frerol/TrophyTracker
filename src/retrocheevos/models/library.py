"""Library DTOs — map to `rom_folders` and `installed_roms` (Database.md 3.1, 3.2)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RomFolder:
    path: str
    watch_enabled: bool
    console_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class InstalledRom:
    file_path: str
    hash: str
    console_id: int
    game_id: Optional[int] = None
    detected_at: Optional[datetime] = None
    id: Optional[int] = None
