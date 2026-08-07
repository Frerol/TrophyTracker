"""Scaling shared by every cover-art card.

RA's artwork is not one shape: some entries are square icons, others are box
art at 4:3 or taller. Scaled with `KeepAspectRatio` into a square box, a
square source fills it edge to edge while a 4:3 source is letterboxed — so a
grid of cards showed visibly different picture sizes even though every card
was identical.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap


def fill_square(pixmap: QPixmap, size: QSize) -> QPixmap:
    """Scale `pixmap` to cover `size` completely, then centre-crop to it.

    `KeepAspectRatioByExpanding` guarantees both dimensions reach the target,
    so nothing is letterboxed; the crop then takes the middle, which is where
    box art puts its subject. Aspect ratio is preserved — the image is never
    stretched, only trimmed at the long edge.
    """
    if pixmap.isNull():
        return pixmap
    scaled = pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    return scaled.copy(x, y, size.width(), size.height())
