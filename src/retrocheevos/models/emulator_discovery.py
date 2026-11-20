"""Results of a local emulator search."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class EmulatorCandidate:
    name: str
    executable_path: str
    requires_core: bool = False
    flatpak_app_id: Optional[str] = None
    flatpak_installation: Optional[str] = None


@dataclass
class EmulatorSearchResult:
    candidates: list[EmulatorCandidate] = field(default_factory=list)
    cancelled: bool = False
    limited: bool = False
    warnings: list[str] = field(default_factory=list)
