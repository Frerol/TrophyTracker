"""Generate TrophyTracker's brand assets from decision D1.

Concept A (pixel trophy) is the application icon at every size the system
draws. Its trophy is a pixel grid, so each size is painted at an integer
scale instead of resampling a vector: edges stay crisp at 16 and 24 px, where
the trophy is also enlarged relative to the tile (the "tight" small variant).
Concept C (cartridge with the same trophy) and the wordmark are rendered from
their SVG masters for large artwork.

Run from the repository root; outputs overwrite the files listed in OUTPUTS::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/brand/generate_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

from retrocheevos.gui import styles
from retrocheevos.gui.assets import load_bundled_fonts

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'assets'
ICONS_DIR = ASSETS / 'icons'
BRAND_DIR = ASSETS / 'brand'
SOURCES = ROOT / 'docs' / 'design' / 'brand-exploration'

# Trophy cells in grid units, taken from concept A's SVG (x, y, width, height).
TROPHY_CELLS = (
    (2, 1, 8, 1), (3, 2, 6, 3), (4, 5, 4, 1), (1, 2, 1, 3), (2, 2, 1, 1), (2, 4, 1, 1),
    (10, 2, 1, 3), (9, 2, 1, 1), (9, 4, 1, 1), (5, 6, 2, 2), (4, 8, 4, 1), (3, 9, 6, 1),
)
# The dark opening in the cup.
TROPHY_NOTCH = (5, 2, 2, 2)
TROPHY_BOUNDS = (1, 1, 10, 9)  # x, y, width, height of the trophy in grid units

# Integer pixels per grid unit for each icon size. 16 and 24 px use a larger
# trophy (62% and 83% of the tile) so the small variant stays legible.
ICON_SCALES = {16: 1, 24: 2, 32: 2, 48: 3, 64: 4, 128: 8, 256: 16, 512: 32}

TILE_COLOR = styles.SURFACE_SIDEBAR
TILE_OUTLINE = styles.SURFACE_RAISED
TROPHY_COLOR = styles.ACCENT_GOLD
NOTCH_COLOR = styles.SURFACE_APP


def render_icon_a(size: int) -> QPixmap:
    scale = ICON_SCALES[size]
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = size * 0.22
    if size >= 32:
        stroke = max(1.0, size / 50)
        painter.setPen(QPen(QColor(TILE_OUTLINE), stroke))
        inset = stroke / 2
        tile = QRectF(inset, inset, size - stroke, size - stroke)
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        tile = QRectF(0, 0, size, size)
    painter.setBrush(QColor(TILE_COLOR))
    painter.drawRoundedRect(tile, radius, radius)

    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(Qt.PenStyle.NoPen)
    bx, by, bw, bh = TROPHY_BOUNDS
    origin_x = (size - bw * scale) // 2 - bx * scale
    origin_y = (size - bh * scale) // 2 - by * scale

    def fill(cell: tuple[int, int, int, int], color: str) -> None:
        x, y, w, h = cell
        painter.fillRect(origin_x + x * scale, origin_y + y * scale, w * scale, h * scale, QColor(color))

    for cell in TROPHY_CELLS:
        fill(cell, TROPHY_COLOR)
    fill(TROPHY_NOTCH, NOTCH_COLOR)
    painter.end()
    return pixmap


def render_svg(path: Path, width: int, height: int) -> QPixmap:
    # QtSvg does not resolve quoted family lists such as "'Space Grotesk',sans-serif"
    # and silently falls back, so name the bundled family directly.
    source = path.read_text(encoding='utf-8').replace(
        "font-family=\"'Space Grotesk',sans-serif\"", f'font-family="{styles.FONT_DISPLAY}"')
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(source.encode('utf-8'))).render(painter, QRectF(0, 0, width, height))
    painter.end()
    return pixmap


def outputs() -> dict[Path, QPixmap]:
    files = {ICONS_DIR / f'trophytracker-{size}.png': render_icon_a(size)
             for size in ICON_SCALES if size <= 256}
    # Single-file fallbacks: desktop/AppImage icon and the header emblem.
    files[ASSETS / 'icon.png'] = render_icon_a(512)
    files[ASSETS / 'logo.png'] = render_icon_a(128)
    files[BRAND_DIR / 'illustration-c-512.png'] = render_svg(
        SOURCES / 'concept-c-cartridge-trophy.svg', 512, 512)
    files[BRAND_DIR / 'wordmark-800.png'] = render_svg(SOURCES / 'wordmark.svg', 800, 280)
    return files


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    if styles.FONT_DISPLAY not in load_bundled_fonts():
        print('Space Grotesk did not load; the wordmark would use a fallback font.', file=sys.stderr)
        return 1
    for path, pixmap in outputs().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not pixmap.save(str(path)):
            print(f'Could not write {path}', file=sys.stderr)
            return 1
        print(f'Wrote {path.relative_to(ROOT)} ({pixmap.width()}x{pixmap.height()})')
    del app
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
