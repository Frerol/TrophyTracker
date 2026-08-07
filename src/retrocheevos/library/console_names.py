"""Short forms for console names, for places where the full name doesn't fit.

Cards under a cover have only the cover's width for their caption, and RA's
console names are long ("PlayStation Portable", "SNES/Super Famicom"). The
abbreviation is what people call them anyway, so this reads better *and*
fits, rather than being an elided stump.

Matching is on the name RA sends, lowercased. Anything unknown falls back to
the full name — a missing entry costs nothing beyond a longer label.
"""

CONSOLE_ABBREVIATIONS = {
    "playstation": "PS1",
    "playstation 2": "PS2",
    "playstation portable": "PSP",
    "game boy": "GB",
    "game boy color": "GBC",
    "game boy advance": "GBA",
    "nintendo 64": "N64",
    "nintendo ds": "NDS",
    "nintendo dsi": "DSi",
    "nintendo entertainment system": "NES",
    "nes/famicom": "NES",
    "snes/super famicom": "SNES",
    "super nintendo entertainment system": "SNES",
    "gamecube": "GCN",
    "genesis/mega drive": "Genesis",
    "mega drive": "Genesis",
    "master system": "SMS",
    "game gear": "GG",
    "sega cd": "SegaCD",
    "sega saturn": "Saturn",
    "saturn": "Saturn",
    "dreamcast": "DC",
    "atari 2600": "A2600",
    "atari 7800": "A7800",
    "atari jaguar": "Jaguar",
    "atari lynx": "Lynx",
    "neo geo pocket": "NGP",
    "pc engine": "PCE",
    "turbografx-16": "PCE",
    "wonderswan": "WS",
    "virtual boy": "VB",
    "arcade": "Arcade",
    "wii": "Wii",
    "wii u": "Wii U",
    "nintendo 3ds": "3DS",
    "msx": "MSX",
    "amiga": "Amiga",
}


def abbreviate_console(name: str) -> str:
    """Short form if there is one, otherwise the name unchanged."""
    if not name:
        return name
    return CONSOLE_ABBREVIATIONS.get(name.strip().casefold(), name)
