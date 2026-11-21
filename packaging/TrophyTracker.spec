# PyInstaller build spec for TrophyTracker.
#
# Build with:   .venv\Scripts\pyinstaller.exe packaging/TrophyTracker.spec
#
# What ships and what does not
# ----------------------------
# SHIPPED: `assets/icon.png`, `assets/logo.png` and `assets/fonts/` (Inter and
# Space Grotesk with their SIL OFL notices), loaded at runtime through
# `gui/assets.py::assets_dir`, which reads `sys._MEIPASS` when frozen.
# Without them the app runs, but with no icon or logo and with fallback fonts.
#
# NOT SHIPPED, deliberately:
#   database/  — one person's account, API key, library and preferences.
#                Nothing here would be right for anyone else, and shipping it
#                would hand over a RetroAchievements API key.
#   logs/      — a record of what one person did with the app.
#   cache/     — downloaded artwork, including the profile pictures of the
#                developer's account and everyone they follow.
#
# Neither is excluded by a rule below: PyInstaller only bundles what a spec
# names; this spec names runtime artwork and the optional licensed helper.
# Historical reference artwork is not bundled. The `excludes` entry
# exists so an accidental `--add-data .` or a future edit that sweeps the
# project root can't pull them in silently.
#
# The database is not "missing" in the built app — `database/connection.py`
# creates a fresh one under %LOCALAPPDATA%\Retrocheevos on first run, per
# Windows user. That is what makes handing the .exe to someone else safe:
# they start empty and build their own.

from pathlib import Path
import sys

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis

BLOCK_CIPHER = None

# RAHasher — RetroAchievements' own hasher, used by `library/rahasher.py` when
# present. Bundled only if placed in `tools/rahasher/`; the build
# works either way and the app degrades to its built-in hashing without it.
#
# RAHasher is kept with its license/source notice under tools/rahasher/.
# It is built from RALibretro, which is
# GPL-3.0 (the `rcheevos` hashing code inside it is MIT, but the binary as
# distributed is not). Invoking it as a separate process is aggregation, not
# linking, so it does not make this app GPL — but *redistributing* the binary
# carries GPL-3.0 obligations: ship its license text and either the
# corresponding source or a written offer for it. `tools/rahasher/` is therefore
# expected to hold `RAHasher.exe` alongside `RAHasher-COPYING.txt` and a
# `RAHasher-SOURCE.txt` naming the exact upstream tag the binary came from,
# and all three ship together or none do.
# SPECPATH is provided by PyInstaller and points to this spec's directory.
# Resolve input files independently of the directory from which it was invoked.
_PROJECT_ROOT = Path(SPECPATH).resolve().parent
_TOOLS_DIR = _PROJECT_ROOT / "tools" / "rahasher"
_BUNDLE_TOOLS_DIR = "tools/rahasher"
_RAHASHER = _TOOLS_DIR / ("RAHasher.exe" if sys.platform == "win32" else "RAHasher")
_RAHASHER_LICENSE_FILES = ("RAHasher-COPYING.txt", "RAHasher-SOURCE.txt")

if _RAHASHER.is_file():
    missing = [name for name in _RAHASHER_LICENSE_FILES if not (_TOOLS_DIR / name).is_file()]
    if missing:
        raise SystemExit(
            f"{_RAHASHER} is present but {', '.join(missing)} is not. "
            "RAHasher is GPL-3.0; redistributing the binary without its license "
            "text and a pointer to the corresponding source is a licence "
            "violation. Add the missing file(s), or remove RAHasher.exe to build "
            "without it."
        )
    rahasher_binaries = [(str(_RAHASHER), _BUNDLE_TOOLS_DIR)]
    rahasher_datas = [(str(_TOOLS_DIR / name), _BUNDLE_TOOLS_DIR) for name in _RAHASHER_LICENSE_FILES]
    print(f"packaging/TrophyTracker.spec: bundling {_RAHASHER} and its licence files")
else:
    rahasher_binaries = []
    rahasher_datas = []
    print(f"packaging/TrophyTracker.spec: no {_RAHASHER} — building without it")

analysis = Analysis(
    [str(_PROJECT_ROOT / "src" / "retrocheevos" / "main.py")],
    pathex=[str(_PROJECT_ROOT / "src")],
    binaries=rahasher_binaries,
    # (source, destination-inside-the-bundle)
    datas=[
        (str(_PROJECT_ROOT / "assets" / "icon.png"), "assets"),
        (str(_PROJECT_ROOT / "assets" / "logo.png"), "assets"),
        # Inter and Space Grotesk with their SIL OFL notices (R17).
        (str(_PROJECT_ROOT / "assets" / "fonts"), "assets/fonts"),
        *rahasher_datas,
    ],
    # `keyring` picks its backend at runtime through entry points, so nothing
    # in the source ever names `keyring.backends.Windows` — PyInstaller's
    # static analysis cannot see it and the frozen app would fall back to the
    # "no vault available" path, silently keeping API keys in the database.
    # `win32ctypes` is what the Windows backend calls into.
    hiddenimports=[
        "keyring.backends.Windows",
        "win32ctypes.core",
        "win32ctypes.core.ctypes",
    ] if sys.platform == "win32" else ["keyring.backends.SecretService"],
    hookspath=[],
    runtime_hooks=[],
    # Belt and braces — see the note above. Also drops Qt modules PySide6
    # pulls in by default that this app never touches, which is most of the
    # size difference in the finished build.
    excludes=[
        "database",
        "logs",
        "cache",
        "tkinter",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=BLOCK_CIPHER)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TrophyTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # False = no console window behind the GUI. Flip to True temporarily if
    # the built app fails to start and you need to see the traceback; the
    # crash handler in `main.py` also writes one to
    # %LOCALAPPDATA%\Retrocheevos\logs\crash.log either way.
    console=False,
    icon=str(_PROJECT_ROOT / "assets" / "icon.png"),
)

# One folder, not one file. A one-file build re-extracts the whole bundle to
# a temp directory on every launch, which for a Qt app is a visible delay,
# and it makes `sys._MEIPASS` paths change between runs. A folder starts
# faster and is easier to inspect when something is missing — zip it to hand
# over.
COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="TrophyTracker",
)
