"""Paint-only Library card (R22): cover, title, console, progress and Play.

No widgets per card (R07/R17): everything is painted, and the Play button is
hit-tested in `editorEvent`, the same widget-less approach as Explorer's
`ActionsDelegate`. Play is drawn disabled, with "No emulator" beside it, when
the card's console has no configured emulator.
"""

from typing import Optional

from PySide6.QtCore import QEvent, QModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from retrocheevos.gui import styles
from retrocheevos.gui.models.library_grid_model import (
    COVER_EDGE, CaptionRole, FallbackRole, PlayReasonRole, ProgressRole,
)

PADDING = 12
GAP = 6
TITLE_LINES = 2
BAR_HEIGHT = 6
BUTTON_HEIGHT = 34
BUTTON_WIDTH = 76
CARD_HEIGHT = PADDING + COVER_EDGE + GAP + 2 * 19 + 18 + GAP + BAR_HEIGHT + GAP + BUTTON_HEIGHT + PADDING
MIN_CARD_WIDTH = 200
CELL_MARGIN = 6
# Grid cell = card plus the gap around it.
CELL_HEIGHT = CARD_HEIGHT + 2 * CELL_MARGIN


class LibraryCardDelegate(QStyledItemDelegate):
    play_requested = Signal(QModelIndex)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cell = QSize(MIN_CARD_WIDTH, CELL_HEIGHT)
        self._pressed: Optional[QModelIndex] = None

    def set_cell_size(self, size: QSize) -> None:
        self._cell = QSize(size)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return self._cell

    # Geometry ---------------------------------------------------------------

    def card_rect(self, cell: QRect) -> QRect:
        return cell.adjusted(CELL_MARGIN, CELL_MARGIN, -CELL_MARGIN, -CELL_MARGIN)

    def play_rect(self, cell: QRect) -> QRect:
        card = self.card_rect(cell)
        return QRect(card.left() + PADDING, card.bottom() - PADDING - BUTTON_HEIGHT + 1,
                     BUTTON_WIDTH, BUTTON_HEIGHT)

    # Painting ---------------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self.card_rect(option.rect)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        path = QPainterPath()
        path.addRoundedRect(QRectF(card), styles.RADIUS_PANEL, styles.RADIUS_PANEL)
        painter.fillPath(path, QColor(styles.SURFACE_PANEL))
        if focused or selected or hovered:
            color = styles.FOCUS_RING if focused else styles.OUTLINE_MUTED
            painter.setPen(QPen(QColor(color), 2))
            painter.drawPath(path)

        # Cover, centred horizontally.
        cover = QRect(card.center().x() - COVER_EDGE // 2, card.top() + PADDING, COVER_EDGE, COVER_EDGE)
        cover_path = QPainterPath()
        cover_path.addRoundedRect(QRectF(cover), styles.RADIUS_COVER, styles.RADIUS_COVER)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap is not None and not pixmap.isNull():
            painter.save()
            painter.setClipPath(cover_path)
            source = QRect(
                (pixmap.width() - COVER_EDGE) // 2, (pixmap.height() - COVER_EDGE) // 2,
                COVER_EDGE, COVER_EDGE,
            )
            painter.drawPixmap(cover, pixmap, source)
            painter.restore()
        else:
            painter.fillPath(cover_path, QColor(styles.SURFACE_RAISED))
            painter.setPen(QColor(styles.TEXT_SECONDARY))
            painter.drawText(cover, Qt.AlignmentFlag.AlignCenter, index.data(FallbackRole) or "")

        text_left = card.left() + PADDING
        text_width = card.width() - 2 * PADDING
        y = cover.bottom() + 1 + GAP

        title_font = QFont(option.font)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(styles.TEXT_PRIMARY))
        title_metrics = QFontMetrics(title_font)
        for line in _elided_lines(index.data(Qt.ItemDataRole.DisplayRole) or "", title_metrics, text_width, TITLE_LINES):
            painter.drawText(QRect(text_left, y, text_width, title_metrics.height()),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
            y += 19

        caption_font = QFont(option.font)
        caption_font.setPixelSize(styles.TYPE_SECONDARY_PX)
        painter.setFont(caption_font)
        painter.setPen(QColor(styles.TEXT_SECONDARY))
        # The short console name keeps the progress readable on narrow cards;
        # the full name is in the tooltip and accessible text.
        caption = f"{index.data(FallbackRole)} · {index.data(CaptionRole)}"
        caption_metrics = QFontMetrics(caption_font)
        painter.drawText(QRect(text_left, y, text_width, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         caption_metrics.elidedText(caption, Qt.TextElideMode.ElideRight, text_width))
        y += 18 + GAP

        fraction = index.data(ProgressRole)
        if fraction is not None:
            track = QRectF(text_left, y, text_width, BAR_HEIGHT)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(styles.PROGRESS_TRACK))
            painter.drawRoundedRect(track, BAR_HEIGHT / 2, BAR_HEIGHT / 2)
            if fraction > 0:
                painter.setBrush(QColor(styles.ACCENT_GOLD))
                painter.drawRoundedRect(QRectF(text_left, y, max(BAR_HEIGHT, text_width * fraction), BAR_HEIGHT),
                                        BAR_HEIGHT / 2, BAR_HEIGHT / 2)

        # Play button.
        reason = index.data(PlayReasonRole)
        button = self.play_rect(option.rect)
        button_path = QPainterPath()
        button_path.addRoundedRect(QRectF(button), styles.RADIUS_CONTROL, styles.RADIUS_CONTROL)
        enabled = reason is None
        painter.fillPath(button_path, QColor(styles.ACCENT_GOLD if enabled else styles.SURFACE_RAISED))
        button_font = QFont(option.font)
        button_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(button_font)
        painter.setPen(QColor(styles.TEXT_ON_ACCENT if enabled else styles.TEXT_DISABLED))
        painter.drawText(button, Qt.AlignmentFlag.AlignCenter, "Play")
        if reason:
            painter.setFont(caption_font)
            painter.setPen(QColor(styles.TEXT_SECONDARY))
            reason_rect = QRect(button.right() + GAP + 2, button.top(),
                                card.right() - PADDING - button.right() - GAP, button.height())
            painter.drawText(reason_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             caption_metrics.elidedText(reason, Qt.TextElideMode.ElideRight, reason_rect.width()))
        painter.restore()

    # Interaction --------------------------------------------------------------

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802 — Qt override
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if self.play_rect(option.rect).contains(event.position().toPoint()):
                self._pressed = QModelIndex(index)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            pressed, self._pressed = self._pressed, None
            if (
                pressed is not None and pressed == index
                and self.play_rect(option.rect).contains(event.position().toPoint())
            ):
                if index.data(PlayReasonRole) is None:
                    self.play_requested.emit(QModelIndex(index))
                return True
        return super().editorEvent(event, model, option, index)


def _elided_lines(text: str, metrics: QFontMetrics, width: int, max_lines: int) -> list[str]:
    """Word-wrap `text` into at most `max_lines`, eliding the last one."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for position, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if metrics.horizontalAdvance(candidate) <= width or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            current = " ".join(words[position:])
            break
    if current:
        lines.append(metrics.elidedText(current, Qt.TextElideMode.ElideRight, width))
    return [metrics.elidedText(line, Qt.TextElideMode.ElideRight, width) for line in lines[:max_lines]]
