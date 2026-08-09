"""Console auto-detection for ROM folder scanning (Architecture.md — Library
layer).

Used by `library_service.scan_rom_folder` to work out which console a file
belongs to. Since Bloco 11 nothing acts on that answer by moving the file —
a confident result gets the ROM hashed and recorded where it lies, and
anything less gets reported instead.

Extension lookups come from `console_catalog.py` (ported from RA's own
hasher). Unambiguous extensions are trusted outright. For ambiguous ones,
two tie-breakers are tried, in this order:

1. Content. Only `.iso` can be sniffed — for `PSP_GAME/PARAM.SFO` (see
   `psp_hash.looks_like_psp_disc`), the one disc layout this codebase can
   currently parse with confidence. What's actually inside the file beats
   anything inferred from where it sits.
2. `folder_console_id`, the console the user declared for the ROM folder
   being scanned. Applied only when it is already one of the extension's
   candidates.

Anything still ambiguous after that is left unresolved on purpose: guessing
wrong here means silently filing a ROM under the wrong console, which is
worse than asking.

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


def detect_console(
    file_path: Path, folder_console_id: Optional[int] = None
) -> DetectionResult:
    """`folder_console_id` is the console the ROM folder is configured for, if
    any — a tie-breaker between an extension's candidates, never more than
    that. See `_resolve` for why it stops there.
    """
    extension = file_path.suffix.lstrip(".")

    if extension.lower() == "zip":
        zip_result = _detect_single_file_zip(file_path, folder_console_id)
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

    return _resolve(candidates, folder_console_id)


def _resolve(
    candidates: tuple[int, ...],
    folder_console_id: Optional[int],
    inner_member: Optional[str] = None,
) -> DetectionResult:
    """Last word on an ambiguous extension: take the folder's declared console
    if the extension could plausibly be it, otherwise stay ambiguous.

    Disc-based consoles are where scanning kept coming up empty. `.chd`
    covers nine consoles, `.cue` nine, `.bin` five, `.iso` six — a folder of
    PS1 or PS2 games is a folder where *every* file is ambiguous, so a
    correctly configured ROM folder could scan to zero results. The console
    the user picked for that folder was sitting in `rom_folders.console_id`
    the whole time and nothing read it.

    Deliberately only a tie-breaker. An extension RA maps to nothing at all
    (`.cso`, say) stays unrecognized rather than being claimed by the folder:
    the extension list is what says whether this codebase can hash the format
    correctly, and a folder label is a statement about consoles, not formats.
    Nor does it override a single-candidate extension — a `.gba` in a folder
    labelled SNES is a misfiled ROM, not a Super Nintendo game.
    """
    if folder_console_id is not None and folder_console_id in candidates:
        return DetectionResult(console_id=folder_console_id, inner_member=inner_member)
    return DetectionResult(candidate_console_ids=candidates, inner_member=inner_member)


def _detect_single_file_zip(
    zip_path: Path, folder_console_id: Optional[int]
) -> Optional[DetectionResult]:
    member_name = find_single_rom_member(zip_path)
    if member_name is None:
        return None

    inner_extension = Path(member_name).suffix.lstrip(".")
    candidates = get_candidate_console_ids(inner_extension)
    if not candidates:
        return None

    if len(candidates) == 1:
        return DetectionResult(console_id=candidates[0], inner_member=member_name)

    return _resolve(candidates, folder_console_id, inner_member=member_name)
