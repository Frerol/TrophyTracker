"""Console dropdown with a bounded, scrollable popup on native Qt themes."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QListView, QWidget

MAX_VISIBLE_CONSOLES = 10
POPUP_MAX_HEIGHT = 300


class ConsoleSelector(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMaxVisibleItems(MAX_VISIBLE_CONSOLES)
        # Some native menu-style popups ignore maxVisibleItems. Use a list
        # popup explicitly so every platform gets the same scrolling behavior.
        self.setStyleSheet('QComboBox { combobox-popup: 0; }')
        view = QListView(self)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setMaximumHeight(POPUP_MAX_HEIGHT)
        self.setView(view)
