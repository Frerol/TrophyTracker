"""Inline row-remove control for simple `QListWidget` management lists
(Settings' ROM Folders/Emulators/ROM Destinations/Blocked Games) —
presentation-only (Architecture.md §3.1).

Paints a small "-" button at the right edge of each row and detects clicks
via `editorEvent`, rather than a real embedded `QWidget` via
`QListWidget.setItemWidget()` — that's the same underlying
`QAbstractItemView::setIndexWidget()` mechanism already implicated in a
native crash on the Explorer table (`gui/delegates/explorer_delegates.py`'s
`ActionsDelegate`, which this mirrors). These lists are small, so nothing
here is about performance — it's about not reintroducing a mechanism
already shown to be fragile, even at a scale where it's unlikely to bite.
"""

from typing import Optional

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
)

BUTTON_SIZE = 18
BUTTON_MARGIN = 6
TEXT_MARGIN = 4


class RemovableListDelegate(QStyledItemDelegate):
    """One instance per list, connected to that list's own removal handler
    — the id it emits is whatever the row stored in `Qt.ItemDataRole.UserRole`
    (already set by every caller of this delegate, for the existing
    "Remove Selected"-style button).
    """

    remove_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pressed: Optional[QPersistentModelIndex] = None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))
            text_color = option.palette.color(QPalette.ColorRole.HighlightedText)
        else:
            text_color = option.palette.color(QPalette.ColorRole.Text)

        button_rect = self._button_rect(option)
        text_rect = QRect(
            option.rect.left() + TEXT_MARGIN,
            option.rect.top(),
            button_rect.left() - option.rect.left() - TEXT_MARGIN,
            option.rect.height(),
        )
        painter.setPen(text_color)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            option.fontMetrics.elidedText(
                index.data(Qt.ItemDataRole.DisplayRole) or "", Qt.TextElideMode.ElideRight, text_rect.width()
            ),
        )

        style = option.widget.style() if option.widget else QApplication.style()
        button_option = QStyleOptionButton()
        button_option.rect = button_rect
        button_option.text = "−"  # minus sign
        button_option.state = QStyle.StateFlag.State_Enabled
        button_option.state |= (
            QStyle.StateFlag.State_Sunken
            if self._pressed == QPersistentModelIndex(index)
            else QStyle.StateFlag.State_Raised
        )
        style.drawControl(QStyle.ControlElement.CE_PushButton, button_option, painter, option.widget)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(base.height(), BUTTON_SIZE + 2 * BUTTON_MARGIN))

    def editorEvent(
        self, event: QEvent, model, option: QStyleOptionViewItem, index: QModelIndex
    ) -> bool:
        if event.type() not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            return False

        persistent_index = QPersistentModelIndex(index)
        hit = self._button_rect(option).contains(event.position().toPoint())

        if event.type() == QEvent.Type.MouseButtonPress:
            if not hit:
                return False
            self._pressed = persistent_index
            self._repaint_cell(option)
            return True

        pressed = self._pressed
        self._pressed = None
        self._repaint_cell(option)
        if pressed is None or pressed != persistent_index or not hit:
            return False

        item_id = index.data(Qt.ItemDataRole.UserRole)
        if item_id is None:
            return False
        self.remove_requested.emit(item_id)
        return True

    def _button_rect(self, option: QStyleOptionViewItem) -> QRect:
        return QRect(
            option.rect.right() - BUTTON_SIZE - BUTTON_MARGIN,
            option.rect.top() + (option.rect.height() - BUTTON_SIZE) // 2,
            BUTTON_SIZE,
            BUTTON_SIZE,
        )

    def _repaint_cell(self, option: QStyleOptionViewItem) -> None:
        if option.widget:
            option.widget.update(option.rect)
