"""Helpers that keep a view's position while its content is rebuilt (R18)."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QScrollArea


def restore_scroll_later(area: QScrollArea, value: int) -> None:
    """Return `area` to vertical position `value` once its new content is laid out.

    Rebuilt rows only get their final height after the pending layout
    request is handled, so the position is applied on the next event-loop
    pass and clamped to the new range.
    """
    def restore() -> None:
        content = area.widget()
        if content is not None and content.layout() is not None:
            content.layout().activate()
        bar = area.verticalScrollBar()
        bar.setValue(min(value, bar.maximum()))

    if value > 0:
        QTimer.singleShot(0, area, restore)
