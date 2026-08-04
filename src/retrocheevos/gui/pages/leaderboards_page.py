"""Leaderboards page — placeholder.

Leaderboards is Version 1.2 scope (DevelopmentRoadmap.md); no api/ or
services/ backend exists for it yet, unlike the other MVP pages.
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.base_page import Page


class LeaderboardsPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Leaderboards are coming in Version 1.2."))
        layout.addStretch(1)
