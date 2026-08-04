"""Console auto-detection for Watch Folder scanning (Architecture.md —
Library layer, "console-folder organizer").

Extension lookups come from `console_catalog.py` (ported from RA's own
hasher). Unambiguous extensions are trusted outright. For ambiguous ones,
this module only ever resolves `.iso` — by sniffing for
`PSP_GAME/PARAM.SFO` (see `psp_hash.looks_like_psp_disc`), the one disc
layout this codebase can currently parse with confidence. Anything else
ambiguous is left unresolved on purpose: guessing wrong here means silently
filing a ROM under the wrong console, which is worse than asking.

`.zip` gets one extra pre-check: if it contains exactly one file, detection
runs again against *that file's* extension instead of trusting the `.zip`
extension's own (Arcade) mapping — see `zip_extraction.py`. No content
sniffing happens inside a zip (e.g. a lone ambiguous `.iso` member still
comes back ambiguous) — PSP discs are rarely distributed zipped, so that
gap isn't worth the added complexity yet.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from retrocheevos.library import psp_hash
from retrocheevos.library.console_catalog import get_candidate_console_ids
from retrocheevos.library.zip_extraction import find_single_rom_member


@dataclass
class DetectionResult:
    console_id: Optional[int] = None
    candidate_console_ids: tuple[int, ...] = field(default_factory=tuple)
    inner_member: Optional[str] = None
    """Set when `console_id`/`candidate_console_ids` came from peeking inside
    a single-file zip — the name of that file within the archive. `None`
    means the match is for `file_path` itself.
    """

    @property
    def is_confident(self) -> bool:
        return self.console_id is not None

    @property
    def is_recognized(self) -> bool:
        return self.console_id is not None or bool(self.candidate_console_ids)


def detect_console(file_path: Path) -> DetectionResult:
    extension = file_path.suffix.lstrip(".")

    if extension.lower() == "zip":
        zip_result = _detect_single_file_zip(file_path)
        if zip_result is not None:
            return zip_result
        # Not a single-file zip (or its one member isn't a recognized ROM
        # extension either) — fall through to the normal `.zip` handling below.

    candidates = get_candidate_console_ids(extension)
    if not candidates:
        return DetectionResult()

    if len(candidates) == 1:
        return DetectionResult(console_id=candidates[0])

    if extension.lower() == "iso" and psp_hash.PSP_CONSOLE_ID in candidates:
        if psp_hash.looks_like_psp_disc(file_path):
            return DetectionResult(console_id=psp_hash.PSP_CONSOLE_ID)

    return DetectionResult(candidate_console_ids=candidates)


def _detect_single_file_zip(zip_path: Path) -> Optional[DetectionResult]:
    member_name = find_single_rom_member(zip_path)
    if member_name is None:
        return None

    inner_extension = Path(member_name).suffix.lstrip(".")
    candidates = get_candidate_console_ids(inner_extension)
    if not candidates:
        return None

    if len(candidates) == 1:
        return DetectionResult(console_id=candidates[0], inner_member=member_name)

    return DetectionResult(candidate_console_ids=candidates, inner_member=member_name)
