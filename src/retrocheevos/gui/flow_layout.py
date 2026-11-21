"""A layout that places items left to right and wraps them onto new rows.

Used for rows of chips and buttons that must stay reachable when the window
is narrow (R18, minimum 1024×720) instead of being clipped. Adapted from the
Qt "Flow Layout" example.
"""

from typing import Optional

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent: Optional[QWidget] = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        if parent is not None:
            self.setContentsMargins(QMargins(0, 0, 0, 0))

    def __del__(self) -> None:
        while self.takeAt(0) is not None:
            pass

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 — Qt override
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802 — Qt override
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802 — Qt override
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def spacing(self) -> int:
        return self._spacing

    def setSpacing(self, spacing: int) -> None:  # noqa: N802 — Qt override
        self._spacing = spacing
        self.invalidate()

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 — Qt override
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 — Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 — Qt override
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 — Qt override
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 — Qt override
        # Preferred: everything on one row.
        width = sum(item.sizeHint().width() for item in self._items)
        width += self._spacing * max(0, len(self._items) - 1)
        height = max((item.sizeHint().height() for item in self._items), default=0)
        margins = self.contentsMargins()
        return QSize(width + margins.left() + margins.right(), height + margins.top() + margins.bottom())

    def minimumSize(self) -> QSize:  # noqa: N802 — Qt override
        # Narrowest: the widest single item.
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, row_height = area.x(), area.y(), 0
        # Items of the current row, placed once the row's height is known so
        # each is centred vertically (a search field beside shorter chips).
        row: list[tuple[QLayoutItem, int]] = []

        def place_row() -> None:
            if apply:
                for placed, left in row:
                    hint = placed.sizeHint()
                    top = y + (row_height - hint.height()) // 2
                    placed.setGeometry(QRect(QPoint(left, top), hint))
            row.clear()

        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > area.right() + 1 and row_height > 0:
                place_row()
                x = area.x()
                y += row_height + self._spacing
                next_x = x + hint.width() + self._spacing
                row_height = 0
            row.append((item, x))
            x = next_x
            row_height = max(row_height, hint.height())
        place_row()
        return y + row_height - rect.y() + margins.bottom()
