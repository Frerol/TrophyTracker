"""Common base for gui/ pages (Architecture.md: view logic only, talks to services/)."""

from PySide6.QtWidgets import QWidget

from retrocheevos.gui.app_context import AppContext


class Page(QWidget):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__()
        self.app_context = app_context

    def refresh(self) -> None:
        """Reload this page's data from services/. Called when the page becomes visible."""
