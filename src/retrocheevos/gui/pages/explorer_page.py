"""Explorer page (UI.md 3.2) — "the heart of the app".

Skeleton scope: search text + default filters (Completed/Abandoned/Mastered
hidden) + Game Cards, plus a minimal sync affordance (Sync Consoles / Sync
Games for Console) since nothing else populates local game data yet. Full
filter bar and Random button are deferred to the deepening pass.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.core.explorer import ExplorerFilters
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.services import (
    console_service,
    explorer_service,
    library_service,
    lists_service,
    session_service,
    sync_service,
)
from retrocheevos.utils.enums import ListType
from retrocheevos.widgets.game_card import GameCard

GRID_COLUMNS = 4


class ExplorerPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._worker: Optional[ServiceWorker] = None
        self._play_worker: Optional[ServiceWorker] = None

        self._console_selector = QComboBox()
        self._sync_consoles_button = QPushButton("Sync Consoles")
        self._sync_consoles_button.clicked.connect(self._on_sync_consoles)
        self._sync_games_button = QPushButton("Sync Games for Console")
        self._sync_games_button.clicked.connect(self._on_sync_games)

        sync_bar = QHBoxLayout()
        sync_bar.addWidget(self._console_selector)
        sync_bar.addWidget(self._sync_consoles_button)
        sync_bar.addWidget(self._sync_games_button)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search games...")
        self._search_input.returnPressed.connect(self.refresh)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._grid_container)

        layout = QVBoxLayout(self)
        layout.addLayout(sync_bar)
        layout.addWidget(self._search_input)
        layout.addWidget(scroll_area)

    def refresh(self) -> None:
        console_names = self._populate_console_selector()
        self._clear_grid()

        account = self.app_context.active_account
        if account is None:
            return

        filters = ExplorerFilters(search_text=self._search_input.text().strip() or None)
        results = explorer_service.get_games(account.id, filters)
        for index, result in enumerate(results):
            card = GameCard(
                result.game,
                result.percent_complete,
                console_name=console_names.get(result.game.console_id),
            )
            card.list_action_requested.connect(self._on_list_action)
            card.play_requested.connect(self._on_play)
            self._grid_layout.addWidget(card, index // GRID_COLUMNS, index % GRID_COLUMNS)

    def _populate_console_selector(self) -> dict[int, str]:
        """Refills the console dropdown and returns an id -> name map for Game Cards."""
        consoles = console_service.list_consoles()

        previous = self._console_selector.currentData()
        self._console_selector.blockSignals(True)
        self._console_selector.clear()
        for console in consoles:
            self._console_selector.addItem(console.name, console.id)
        if previous is not None:
            index = self._console_selector.findData(previous)
            if index >= 0:
                self._console_selector.setCurrentIndex(index)
        self._console_selector.blockSignals(False)

        return {console.id: console.name for console in consoles}

    def _clear_grid(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_list_action(self, game_id: int, list_type: ListType) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        lists_service.add_to_list(account.id, game_id, list_type)

    def _on_sync_consoles(self) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        client = session_service.build_api_client(account)
        self._sync_consoles_button.setEnabled(False)
        self._worker = ServiceWorker(sync_service.sync_consoles, client)
        self._worker.finished_ok.connect(self._on_sync_consoles_done)
        self._worker.failed.connect(self._on_sync_failed)
        self._worker.start()

    def _on_sync_consoles_done(self, _result: object) -> None:
        self._sync_consoles_button.setEnabled(True)
        self._populate_console_selector()

    def _on_sync_games(self) -> None:
        account = self.app_context.active_account
        console_id = self._console_selector.currentData()
        if account is None or console_id is None:
            return
        client = session_service.build_api_client(account)
        self._sync_games_button.setEnabled(False)
        self._worker = ServiceWorker(sync_service.sync_games_for_console, client, console_id)
        self._worker.finished_ok.connect(self._on_sync_games_done)
        self._worker.failed.connect(self._on_sync_failed)
        self._worker.start()

    def _on_sync_games_done(self, _result: object) -> None:
        self._sync_games_button.setEnabled(True)
        self.refresh()

    def _on_sync_failed(self, message: str) -> None:
        self._sync_consoles_button.setEnabled(True)
        self._sync_games_button.setEnabled(True)
        QMessageBox.warning(self, "Sync failed", message)

    def _on_play(self, game_id: int) -> None:
        self._play_worker = ServiceWorker(library_service.launch_game, game_id)
        self._play_worker.failed.connect(self._on_play_failed)
        self._play_worker.start()

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)
