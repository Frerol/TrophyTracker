"""Derives a clean display title from a ROM's filename, and matches that
title against RetroAchievements' own catalog titles.

Used for `installed_roms` rows with no matched game — both to label them in
Continue Playing (`services/dashboard_service.py`'s fallback), and to
pre-select a likely match in the "Match to Game..." dialog
(`gui/dialogs/match_rom_dialog.py`).

Deliberately simple: strips extension and parenthesized/bracketed tags
("(USA)", "[!]"), normalizes separators. Doesn't attempt to parse every
scene-release naming convention — just the tags the feature was asked to
clean up.
"""

import difflib
import re
from pathlib import Path
from typing import Optional

_TAG_PATTERN = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_SEPARATOR_PATTERN = re.compile(r"[_.]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")

# RetroAchievements marks non-retail entries with `~Prefix~` in the title
# itself ("~Prototype~ Diablo", "~Homebrew~ Coin Fall"). A ROM filename
# never carries these, so they're pure noise when comparing — and they hurt
# disproportionately: "Diablo" vs "~Prototype~ Diablo" scores only 0.50 on
# a raw ratio purely because of the prefix's length.
_RA_MARKER_PATTERN = re.compile(r"~[^~]*~")
_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9 ]")

# Only reached when neither an exact nor a whole-word containment match
# exists, so it's a genuine last resort rather than the primary mechanism.
FUZZY_MATCH_CUTOFF = 0.6
# Looser, for picking *cover art* rather than suggesting a game to match.
# The two decisions carry different costs: proposing the wrong game invites
# the user to record a wrong match, while a wrong picture is just a wrong
# picture and no worse than the blank placeholder it replaces. Being strict
# there and lenient here is deliberate, not an inconsistency.
COVER_MATCH_CUTOFF = 0.45


def derive_title_from_filename(file_path: str) -> str:
    """'Secret Agent Clank (USA) (En,Fr).iso' -> 'Secret Agent Clank'."""
    stem = _TAG_PATTERN.sub("", Path(file_path).stem)
    stem = _SEPARATOR_PATTERN.sub(" ", stem)
    stem = _WHITESPACE_PATTERN.sub(" ", stem).strip()
    return stem or Path(file_path).stem


def _normalize_for_matching(title: str) -> str:
    """Strips RA's `~Prefix~` markers, punctuation and case, so only the
    words that both sides actually share are compared.
    """
    normalized = _RA_MARKER_PATTERN.sub(" ", title.lower())
    normalized = _NON_ALPHANUMERIC_PATTERN.sub(" ", normalized)
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def find_best_title_match(
    derived_title: str,
    candidate_titles: list[str],
    cutoff: float = FUZZY_MATCH_CUTOFF,
) -> Optional[str]:
    """Best guess at which catalog title a ROM's derived title refers to, or
    None when nothing is close enough to be worth suggesting.

    Tried in order — exact normalized equality, then whole-word containment
    either way round, then fuzzy similarity. Containment matters more than
    it looks: scene-release names bolt extra words on ("Secret Agent Clank
    EUR MULTI12 RETAIL PSP-ZER0") while RA titles bolt on their own
    ("~Prototype~ Diablo"), and a raw similarity ratio handles neither well.
    The shortest containment match wins, so "Diablo" doesn't get captured by
    some longer title that merely includes the word.
    """
    needle = _normalize_for_matching(derived_title)
    if not needle:
        return None

    normalized_candidates = [_normalize_for_matching(title) for title in candidate_titles]

    for index, candidate in enumerate(normalized_candidates):
        if candidate == needle:
            return candidate_titles[index]

    best_index: Optional[int] = None
    for index, candidate in enumerate(normalized_candidates):
        if not candidate:
            continue
        if f" {needle} " in f" {candidate} " or f" {candidate} " in f" {needle} ":
            if best_index is None or len(candidate) < len(normalized_candidates[best_index]):
                best_index = index
    if best_index is not None:
        return candidate_titles[best_index]

    matches = difflib.get_close_matches(
        needle, normalized_candidates, n=1, cutoff=cutoff
    )
    if not matches:
        return None
    return candidate_titles[normalized_candidates.index(matches[0])]
