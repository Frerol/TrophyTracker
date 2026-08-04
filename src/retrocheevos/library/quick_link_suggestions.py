"""Curated default Quick Link suggestions — a starting point Settings can
pre-fill, never auto-applied without the user seeing/accepting it first.
The app never fetches anything from these; only used to pre-fill a form
field with a URL the user then opens (or edits/clears) manually.

Deliberately small, not exhaustive: only consoles with a specific,
verified-at-write-time resource are listed here (see comments per entry).
No entry here means no strong recommendation was found, not "no homebrew
scene" — the user can still set any URL manually for any console.

Keyed by the exact console name strings RetroAchievements syncs (checked
against a real synced `consoles` table), matching how every other
console-keyed Settings entry in this app works (`EmulatorConfig`,
`RomDestination`).
"""

QUICK_LINK_SUGGESTIONS: dict[str, str] = {
    # Homebrew Hub: open-source, API-backed homebrew catalog specifically
    # for the Game Boy family + NES (github.com/gbdev/homebrewhub).
    "Game Boy": "https://hh.gbdev.io/",
    "Game Boy Color": "https://hh.gbdev.io/",
    "Game Boy Advance": "https://hh.gbdev.io/",
    "NES/Famicom": "https://itch.io/games/tag-homebrew/tag-nes",
    # itch.io tag combinations — real, browsable homebrew listings, no
    # official per-console coverage guarantee beyond what's tagged.
    "SNES/Super Famicom": "https://itch.io/games/tag-16-bit/tag-homebrew",
    "Genesis/Mega Drive": "https://itch.io/games/tag-genesis/tag-homebrew",
    # PDRoms: long-running multi-console homebrew archive with a
    # dedicated per-console page.
    "Dreamcast": "https://pdroms.de/files/sega-dreamcast/",
}
