# PyInstaller build spec for Retrocheevos.
#
# Build with:   .venv\Scripts\pyinstaller.exe Retrocheevos.spec
#
# What ships and what does not
# ----------------------------
# SHIPPED: `assets/` (the window icon and the header logo), loaded at runtime
# through `gui/pages/home_page.py::_assets_dir`, which reads `sys._MEIPASS`
# when frozen. Without them bundled the app runs but has no icon or logo.
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
# names, and this one names `assets` and nothing else. The `excludes` entry
# exists so an accidental `--add-data .` or a future edit that sweeps the
# project root can't pull them in silently.
#
# The database is not "missing" in the built app — `database/connection.py`
# creates a fresh one under %LOCALAPPDATA%\Retrocheevos on first run, per
# Windows user. That is what makes handing the .exe to someone else safe:
# they start empty and build their own.

from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis

BLOCK_CIPHER = None

# RAHasher — RetroAchievements' own hasher, used by `library/rahasher.py` when
# present. Bundled only if it has been placed in `tools/` first; the build
# works either way and the app degrades to its built-in hashing without it.
#
# Not committed to this repository, and shipping it is a licensing decision
# rather than an oversight. RAHasher is built from RALibretro, which is
# GPL-3.0 (the `rcheevos` hashing code inside it is MIT, but the binary as
# distributed is not). Invoking it as a separate process is aggregation, not
# linking, so it does not make this app GPL — but *redistributing* the binary
# carries GPL-3.0 obligations: ship its license text and either the
# corresponding source or a written offer for it. `tools/` is therefore
# expected to hold `RAHasher.exe` alongside `RAHasher-COPYING.txt` and a
# `RAHasher-SOURCE.txt` naming the exact upstream tag the binary came from,
# and all three ship together or none do.
_TOOLS_DIR = Path("tools")
_RAHASHER = _TOOLS_DIR / "RAHasher.exe"
_RAHASHER_LICENSE_FILES = ("RAHasher-COPYING.txt", "RAHasher-SOURCE.txt")

if _RAHASHER.is_file():
    missing = [name for name in _RAHASHER_LICENSE_FILES if not (_TOOLS_DIR / name).is_file()]
    if missing:
        raise SystemExit(
            f"tools/RAHasher.exe is present but {', '.join(missing)} is not. "
            "RAHasher is GPL-3.0; redistributing the binary without its license "
            "text and a pointer to the corresponding source is a licence "
            "violation. Add the missing file(s), or remove RAHasher.exe to build "
            "without it."
        )
    rahasher_binaries = [(str(_RAHASHER), "tools")]
    rahasher_datas = [(str(_TOOLS_DIR / name), "tools") for name in _RAHASHER_LICENSE_FILES]
    print(f"Retrocheevos.spec: bundling {_RAHASHER} and its licence files")
else:
    rahasher_binaries = []
    rahasher_datas = []
    print("Retrocheevos.spec: no tools/RAHasher.exe — building without it")

analysis = Analysis(
    ["src/retrocheevos/main.py"],
    pathex=["src"],
    binaries=rahasher_binaries,
    # (source, destination-inside-the-bundle)
    datas=[("assets", "assets"), *rahasher_datas],
    # `keyring` picks its backend at runtime through entry points, so nothing
    # in the source ever names `keyring.backends.Windows` — PyInstaller's
    # static analysis cannot see it and the frozen app would fall back to the
    # "no vault available" path, silently keeping API keys in the database.
    # `win32ctypes` is what the Windows backend calls into.
    hiddenimports=[
        "keyring.backends.Windows",
        "win32ctypes.core",
        "win32ctypes.core.ctypes",
    ],
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
    name="Retrocheevos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # False = no console window behind the GUI. Flip to True temporarily if
    # the built app fails to start and you need to see the traceback; the
    # crash handler in `main.py` also writes one to
    # %LOCALAPPDATA%\Retrocheevos\logs\crash.log either way.
    console=False,
    icon="assets/icon.png",
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
    name="Retrocheevos",
)
