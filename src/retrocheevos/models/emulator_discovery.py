"""Results of a local emulator search."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmulatorCandidate:
    name: str
    executable_path: str
    requires_core: bool = False


@dataclass
class EmulatorSearchResult:
    candidates: list[EmulatorCandidate] = field(default_factory=list)
    cancelled: bool = False
    limited: bool = False
