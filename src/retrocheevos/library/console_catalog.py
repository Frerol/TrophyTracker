"""Extension -> RetroAchievements console ID mapping (Architecture.md —
Library layer), ported from `rc_hash_iterator_ext_handlers` and its related
`rc_hash_initialize_iterator_*` functions in rcheevos/RAHasher:
https://github.com/RetroAchievements/rcheevos/blob/develop/src/rhash/hash.c

RA's `RC_CONSOLE_*` enum values are the same numeric IDs already stored in
`consoles.id` (Database.md 2.2) — confirmed directly against
https://github.com/RetroAchievements/rcheevos/blob/develop/include/rc_consoles.h
(e.g. `RC_CONSOLE_PSP = 41`, matching our synced "PlayStation Portable" row).

Extensions that map to exactly one console here can be auto-assigned with
confidence. Extensions listing more than one candidate are formats RA itself
only resolves by trying each candidate's disc/container parser in turn
(`rc_hash_iterate`) — `console_detection.py` decides what to do with those;
this module is pure data, no guessing logic.
"""

MEGA_DRIVE = 1
NINTENDO_64 = 2
SUPER_NINTENDO = 3
GAMEBOY = 4
GAMEBOY_ADVANCE = 5
GAMEBOY_COLOR = 6
NINTENDO = 7
PC_ENGINE = 8
SEGA_CD = 9  # RA's own hasher notes: also handles Saturn discs
SEGA_32X = 10
MASTER_SYSTEM = 11
PLAYSTATION = 12
ATARI_LYNX = 13
NEOGEO_POCKET = 14
GAME_GEAR = 15
GAMECUBE = 16
ATARI_JAGUAR = 17
NINTENDO_DS = 18
WII = 19
PLAYSTATION_2 = 21
POKEMON_MINI = 24
ATARI_2600 = 25
MS_DOS = 26
ARCADE = 27
VIRTUAL_BOY = 28
MSX = 29
COMMODORE_64 = 30
SG1000 = 33
AMSTRAD_PC = 37
APPLE_II = 38
DREAMCAST = 40
PSP = 41
THREE_DO = 43
COLECOVISION = 44
PC8800 = 47
PCFX = 49
ATARI_7800 = 51
WONDERSWAN = 53
SUPER_CASSETTEVISION = 55
NEO_GEO_CD = 56
FAIRCHILD_CHANNEL_F = 57
ZX_SPECTRUM = 59
NINTENDO_3DS = 62
SUPERVISION = 63
SHARPX1 = 64
TIC80 = 65
THOMSON_TO8 = 66
ARDUBOY = 71
WASM4 = 72
ELEKTOR_TV_GAMES_COMPUTER = 75
PC_ENGINE_CD = 76
ATARI_JAGUAR_CD = 77
TI83 = 79
UZEBOX = 80

# Extensions RA maps to exactly one console (`rc_hash_initialize_iterator_single`
# entries in the source table).
SINGLE_CONSOLE_EXTENSIONS: dict[str, int] = {
    "2d": SHARPX1,
    "3ds": NINTENDO_3DS,
    "3dsx": NINTENDO_3DS,
    "7z": ARCADE,
    "83g": TI83,
    "83p": TI83,
    "a26": ATARI_2600,
    "a78": ATARI_7800,
    "app": NINTENDO_3DS,
    "arduboy": ARDUBOY,
    "axf": NINTENDO_3DS,
    "bs": SUPER_NINTENDO,
    "cart": SUPER_CASSETTEVISION,
    "cas": MSX,
    "cci": NINTENDO_3DS,
    "chf": FAIRCHILD_CHANNEL_F,
    "cia": NINTENDO_3DS,
    "col": COLECOVISION,
    # A `.cso` is a deflated `.iso`, and only PSP dumps are distributed this
    # way — unlike the plain `.iso` container, which six consoles share, so
    # this one is unambiguous. `library.ciso` inflates it on the fly so
    # `psp_hash` produces the same hash the equivalent `.iso` would.
    "cso": PSP,
    "csw": ZX_SPECTRUM,
    "cxi": NINTENDO_3DS,
    "d64": COMMODORE_64,
    "dosz": MS_DOS,
    "elf": NINTENDO_3DS,
    "fd": THOMSON_TO8,
    "fds": NINTENDO,
    "fig": SUPER_NINTENDO,
    "gb": GAMEBOY,
    "gba": GAMEBOY_ADVANCE,
    "gbc": GAMEBOY_COLOR,
    "gdi": DREAMCAST,
    "gg": GAME_GEAR,
    "hex": ARDUBOY,
    "jag": ATARI_JAGUAR,
    "k7": THOMSON_TO8,
    "lnx": ATARI_LYNX,
    "m5": THOMSON_TO8,
    "m7": THOMSON_TO8,
    "md": MEGA_DRIVE,
    "min": POKEMON_MINI,
    "mx1": MSX,
    "mx2": MSX,
    "n64": NINTENDO_64,
    "ndd": NINTENDO_64,
    "nds": NINTENDO_DS,
    "neo": ARCADE,
    "nes": NINTENDO,
    "ngc": NEOGEO_POCKET,
    "pbp": PSP,
    "pce": PC_ENGINE,
    "pgm": ELEKTOR_TV_GAMES_COMPUTER,
    "pzx": ZX_SPECTRUM,
    "ri": MSX,
    "rom": MSX,  # shared with Thomson TO-8/Fairchild Channel F; RA always picks MSX
    "sap": THOMSON_TO8,
    "scl": ZX_SPECTRUM,
    "sfc": SUPER_NINTENDO,
    "sg": SG1000,
    "sgx": PC_ENGINE,
    "smc": SUPER_NINTENDO,
    "sms": MASTER_SYSTEM,
    "sv": SUPERVISION,
    "swc": SUPER_NINTENDO,
    "tap": COMMODORE_64,  # shared with Oric/ZX Spectrum; RA always picks Commodore 64
    "tic": TIC80,
    "trd": ZX_SPECTRUM,
    "tvc": ELEKTOR_TV_GAMES_COMPUTER,
    "tzx": ZX_SPECTRUM,
    "uze": UZEBOX,
    "v64": NINTENDO_64,
    "vb": VIRTUAL_BOY,
    "wad": WII,
    "wasm": WASM4,
    "woz": APPLE_II,
    "wsc": WONDERSWAN,
    "z64": NINTENDO_64,
    "zip": ARCADE,
}

# Extensions shared by multiple consoles/formats — RA's own hasher only tells
# them apart by trying each candidate's parser in turn. Order matches the
# source's own candidate order (its most-likely-first heuristic), but nothing
# here should be auto-picked without a successful content sniff (see
# console_detection.py) — that's what "ambiguous" means.
AMBIGUOUS_EXTENSION_CANDIDATES: dict[str, tuple[int, ...]] = {
    # rc_hash_initialize_iterator_bin: only checks size to pick a CD-track
    # guess vs. cartridge; still not something we should trust blindly.
    "bin": (THREE_DO, PLAYSTATION, PLAYSTATION_2, SEGA_CD, MEGA_DRIVE),
    # `cso` is deliberately *not* here — it is unambiguously PSP (see
    # SINGLE_CONSOLE_EXTENSIONS); only the plain `.iso` container is shared.
    "chd": (
        PLAYSTATION,
        PLAYSTATION_2,
        DREAMCAST,
        SEGA_CD,
        PSP,
        PC_ENGINE_CD,
        THREE_DO,
        NEO_GEO_CD,
        PCFX,
    ),
    "cue": (
        PLAYSTATION,
        PLAYSTATION_2,
        DREAMCAST,
        SEGA_CD,
        PC_ENGINE_CD,
        THREE_DO,
        PCFX,
        NEO_GEO_CD,
        ATARI_JAGUAR_CD,
    ),
    "d88": (PC8800, SHARPX1),
    "iso": (PLAYSTATION_2, PSP, THREE_DO, SEGA_CD, GAMECUBE, WII),
    "nib": (APPLE_II, COMMODORE_64),
}


def get_candidate_console_ids(extension: str) -> tuple[int, ...]:
    """`extension` without the leading dot, any case. Empty tuple means RA
    has no known mapping for it at all.
    """
    extension = extension.lower()
    single = SINGLE_CONSOLE_EXTENSIONS.get(extension)
    if single is not None:
        return (single,)
    return AMBIGUOUS_EXTENSION_CANDIDATES.get(extension, ())
