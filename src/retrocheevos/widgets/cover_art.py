"""Scaling shared by every cover-art card.

RA's artwork is not one shape: some entries are square icons, others are box
art at 4:3 or taller. Scaled with `KeepAspectRatio` into a square box, a
square source fills it edge to edge while a 4:3 source is letterboxed — so a
grid of cards showed visibly different picture sizes even though every card
was identical.
"""

from PySide6.QtCore import QSize, Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from retrocheevos.gui import styles


def console_placeholder(size: QSize, console_name: str) -> QPixmap:
    """A clear console thumbnail when a title has no published cover art."""
    pixmap = QPixmap(size)
    pixmap.fill(QColor(styles.SURFACE_RAISED))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    edge = min(size.width(), size.height())
    radius = edge * 0.23
    center_x, center_y = size.width() / 2, size.height() * 0.36
    painter.setPen(QPen(QColor(styles.TEXT_SECONDARY), max(1, edge / 60)))
    painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))
    painter.drawEllipse(QRectF(center_x - radius / 5, center_y - radius / 5, radius * 0.4, radius * 0.4))
    font = painter.font()
    font.setPixelSize(max(10, round(edge * 0.16)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(styles.TEXT_PRIMARY))
    painter.drawText(QRectF(2, size.height() * 0.65, size.width() - 4, size.height() * 0.28), Qt.AlignmentFlag.AlignCenter, console_name)
    painter.end()
    return pixmap


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
