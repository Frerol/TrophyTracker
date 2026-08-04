"""Dashboard page (UI.md 3.1) — MVP scope: Continue Playing + Recent Activity.

Recommendations is a placeholder (core/dashboard.py — v1.1 engine). Events
and "Recently added achievements" are out of scope (DevelopmentRoadmap.md).
"""

from typing import Optional

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.services import console_service, dashboard_service, library_service
from retrocheevos.widgets.game_card import GameCard

GRID_COLUMNS = 4


class DashboardPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._play_worker: Optional[ServiceWorker] = None

        self._continue_playing_container = QWidget()
        self._continue_playing_layout = QGridLayout(self._continue_playing_container)
        continue_playing_scroll = QScrollArea()
        continue_playing_scroll.setWidgetResizable(True)
        continue_playing_scroll.setWidget(self._continue_playing_container)

        self._recent_activity_list = QListWidget()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Continue Playing"))
        layout.addWidget(continue_playing_scroll, stretch=2)
        layout.addWidget(QLabel("Recent Activity"))
        layout.addWidget(self._recent_activity_list, stretch=1)
        layout.addWidget(QLabel("Recommendations: coming in v1.1"))

    def refresh(self) -> None:
        self._clear_continue_playing()
        self._recent_activity_list.clear()

        account = self.app_context.active_account
        if account is None:
            return

        console_names = {console.id: console.name for console in console_service.list_consoles()}
        for index, game in enumerate(dashboard_service.get_continue_playing_games(account.id)):
            card = GameCard(game, console_name=console_names.get(game.console_id))
            card.play_requested.connect(self._on_play)
            self._continue_playing_layout.addWidget(card, index // GRID_COLUMNS, index % GRID_COLUMNS)

        for unlock in dashboard_service.get_recent_activity_entries(account.id):
            self._recent_activity_list.addItem(
                f"Achievement #{unlock.achievement_id} unlocked at {unlock.unlocked_at}"
            )

    def _clear_continue_playing(self) -> None:
        while self._continue_playing_layout.count():
            item = self._continue_playing_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_play(self, game_id: int) -> None:
        self._play_worker = ServiceWorker(library_service.launch_game, game_id)
        self._play_worker.failed.connect(self._on_play_failed)
        self._play_worker.start()

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)
