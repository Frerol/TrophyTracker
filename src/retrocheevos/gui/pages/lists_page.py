"""Lists page (UI.md 3.6) — reuses the Game Card, one list type at a time."""

from typing import Optional

from PySide6.QtWidgets import QComboBox, QGridLayout, QMessageBox, QScrollArea, QVBoxLayout, QWidget

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.services import console_service, library_service, lists_service
from retrocheevos.utils.enums import ListType
from retrocheevos.widgets.game_card import GameCard

GRID_COLUMNS = 4

LIST_TYPE_LABELS = {
    ListType.WANT_TO_PLAY: "Want to Play",
    ListType.PLAYING: "Playing",
    ListType.COMPLETED: "Completed",
    ListType.ABANDONED: "Abandoned",
    ListType.FOLLOWING: "Following",
}


class ListsPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._play_worker: Optional[ServiceWorker] = None

        self._list_selector = QComboBox()
        for list_type, label in LIST_TYPE_LABELS.items():
            self._list_selector.addItem(label, list_type)
        self._list_selector.currentIndexChanged.connect(self.refresh)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._grid_container)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list_selector)
        layout.addWidget(scroll_area)

    def refresh(self) -> None:
        self._clear_grid()

        account = self.app_context.active_account
        raw_list_type = self._list_selector.currentData()
        if account is None or raw_list_type is None:
            return
        # QComboBox stores data in a QVariant, which coerces the str-subclass
        # ListType down to a plain str — restore the enum on the way out.
        list_type = ListType(raw_list_type)

        console_names = {console.id: console.name for console in console_service.list_consoles()}
        games = lists_service.get_games_in_list(account.id, list_type)
        for index, game in enumerate(games):
            card = GameCard(game, console_name=console_names.get(game.console_id))
            card.list_action_requested.connect(self._on_list_action)
            card.play_requested.connect(self._on_play)
            self._grid_layout.addWidget(card, index // GRID_COLUMNS, index % GRID_COLUMNS)

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
        self.refresh()

    def _on_play(self, game_id: int) -> None:
        self._play_worker = ServiceWorker(library_service.launch_game, game_id)
        self._play_worker.failed.connect(self._on_play_failed)
        self._play_worker.start()

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)
