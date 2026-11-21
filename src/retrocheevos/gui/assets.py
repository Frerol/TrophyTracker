"""Runtime asset locations and bundled font loading.

Assets live in the project's `assets/` folder when running from source and in
the PyInstaller bundle's `assets/` folder when frozen.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

FONT_FILES = (
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "Inter-Bold.ttf",
    "SpaceGrotesk-Medium.ttf",
    "SpaceGrotesk-Bold.ttf",
)


def assets_dir() -> Path:
    """Where `assets/` lives, from source and from a frozen build.

    PyInstaller unpacks bundled data into a temporary directory it points
    `sys._MEIPASS` at; `__file__` inside the bundle resolves somewhere else.
    Checked at call time, because `_MEIPASS` only exists in a frozen process.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "assets"
    return Path(__file__).resolve().parents[3] / "assets"


def fonts_dir() -> Path:
    return assets_dir() / "fonts"


def sized_icon_path(size: int) -> Path:
    """Pixel-exact render of icon A at `size` px (`tools/brand/generate_icons.py`)."""
    return assets_dir() / "icons" / f"trophytracker-{size}.png"


# Icon A at 512 px: desktop/AppImage icon and fallback for missing sizes.
ICON_PATH = assets_dir() / "icon.png"
# Icon A at 128 px, kept for release artwork.
LOGO_PATH = assets_dir() / "logo.png"


_loaded_families: set[str] | None = None


def load_bundled_fonts() -> set[str]:
    """Register the bundled Inter and Space Grotesk files with Qt.

    Safe to call more than once; later calls return the families registered
    by the first. A missing or unreadable file is logged and skipped, so the
    stylesheet's fallback families take over instead of failing startup.
    """
    global _loaded_families
    if _loaded_families is not None:
        return set(_loaded_families)
    from PySide6.QtGui import QFontDatabase

    families: set[str] = set()
    for name in FONT_FILES:
        path = fonts_dir() / name
        font_id = QFontDatabase.addApplicationFont(str(path)) if path.is_file() else -1
        if font_id < 0:
            logger.warning("Bundled font unavailable: %s", path)
            continue
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    _loaded_families = families
    return set(families)
