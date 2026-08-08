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

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis

BLOCK_CIPHER = None

analysis = Analysis(
    ["src/retrocheevos/main.py"],
    pathex=["src"],
    binaries=[],
    # (source, destination-inside-the-bundle)
    datas=[("assets", "assets")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Belt and braces — see the note above. Also drops Qt modules PySide6
    # pulls in by default that this app never touches, which is most of the
    # size difference in the finished build.
    excludes=[
        "database",
        "logs",
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
