"""Explorer page (UI.md 3.2) — "the heart of the app".

Layout matches RetroAchievements' own game list: a pill filter bar
(`widgets/explorer_filter_bar.py`) above a sortable data table, rather than
a collapsible side panel over a card grid. The table is a plain
`QTableView` + `QSortFilterProxyModel` over `gui/models/explorer_table_model.py`
— `QTableView` only ever paints *visible* rows via delegates
(`gui/delegates/explorer_delegates.py`), including the actions column
(Play/+/Follow), which is painted by `ActionsDelegate` rather than backed
by real embedded widgets. An earlier `QTableView.setIndexWidget()`-based
version of that column was removed after it was implicated in a native
crash (`STATUS_FATAL_USER_CALLBACK_EXCEPTION` inside `Qt6Widgets.dll`,
reproduced across two PySide6 versions) — see `explorer_delegates.py`'s
module docstring for the full story. That means this page now needs no
widget-pool bookkeeping at all: the whole table is plain paint-only
virtualization.

Performance note: every filter/search change re-runs `_refresh_results()`,
NOT the full `refresh()` — `refresh()` also reloads the console checklist
(`_load_consoles()`), which only needs to happen when the page becomes
visible or after a Sync Consoles action, not on every keystroke/checkbox.
"""

import random
from typing import Optional

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
)

from retrocheevos.core.explorer import ExplorerFilters, GameWithCompletion
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.delegates.explorer_delegates import (
    ActionsDelegate,
    ProgressDelegate,
    TitleDelegate,
)
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.models.explorer_table_model import (
    COLUMN_ACTIONS,
    COLUMN_CONSOLE,
    COLUMN_INSTALLED,
    COLUMN_MEDIAN_TIME,
    COLUMN_PROGRESS,
    COLUMN_TITLE,
    COLUMN_TYPE,
    ExplorerTableModel,
)
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.console import Console
from retrocheevos.services import (
    console_service,
    explorer_service,
    library_service,
    lists_service,
    session_service,
    sync_service,
)
from retrocheevos.utils.enums import ListType
from retrocheevos.widgets.explorer_filter_bar import ExplorerFilterBar

ROW_HEIGHT = 48


class ExplorerPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._worker: Optional[ServiceWorker] = None
        self._play_worker: Optional[ServiceWorker] = None
        self._current_results: list[GameWithCompletion] = []
        self._console_names: dict[int, str] = {}
        self._image_loader = ImageLoader()

        self._console_selector = QComboBox()
        self._sync_consoles_button = QPushButton("Sync Consoles")
        self._sync_consoles_button.clicked.connect(self._on_sync_consoles)
        self._sync_games_button = QPushButton("Sync Games for Console")
        self._sync_games_button.clicked.connect(self._on_sync_games)

        sync_bar = QHBoxLayout()
        sync_bar.addWidget(self._console_selector)
        sync_bar.addWidget(self._sync_consoles_button)
        sync_bar.addWidget(self._sync_games_button)
        sync_bar.addStretch(1)

        self._filter_bar = ExplorerFilterBar()
        self._filter_bar.filters_changed.connect(self._refresh_results)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search games...")
        self._search_input.returnPressed.connect(self._refresh_results)

        self._results_count_label = QLabel()

        random_button = QPushButton("Surprise me")
        random_button.clicked.connect(self._on_random)

        search_row = QHBoxLayout()
        search_row.addWidget(self._search_input, stretch=1)
        search_row.addWidget(self._results_count_label)
        search_row.addWidget(random_button)

        self._table_model = ExplorerTableModel(self._image_loader)
        self._proxy_model = QSortFilterProxyModel()
        self._proxy_model.setSourceModel(self._table_model)
        self._proxy_model.setSortRole(Qt.ItemDataRole.EditRole)

        self._table = QTableView()
        self._table.setModel(self._proxy_model)
        self._table.setItemDelegateForColumn(COLUMN_TITLE, TitleDelegate(self._table))
        self._table.setItemDelegateForColumn(COLUMN_PROGRESS, ProgressDelegate(self._table))
        actions_delegate = ActionsDelegate(self._table)
        actions_delegate.play_requested.connect(self._on_play)
        actions_delegate.list_action_requested.connect(self._on_list_action)
        actions_delegate.follow_requested.connect(self._on_follow)
        self._table.setItemDelegateForColumn(COLUMN_ACTIONS, actions_delegate)
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(COLUMN_TITLE, Qt.SortOrder.AscendingOrder)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COLUMN_TITLE, QHeaderView.ResizeMode.Stretch)
        for column in (
            COLUMN_CONSOLE,
            COLUMN_TYPE,
            COLUMN_MEDIAN_TIME,
            COLUMN_INSTALLED,
            COLUMN_PROGRESS,
            COLUMN_ACTIONS,
        ):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        layout = QVBoxLayout(self)
        layout.addLayout(sync_bar)
        layout.addWidget(self._filter_bar)
        layout.addLayout(search_row)
        layout.addWidget(self._table, stretch=1)

    def refresh(self) -> None:
        """Full refresh: reloads consoles (rarely change) and results. Called
        when the page becomes visible — filter/search changes call the
        lighter `_refresh_results()` instead (see module docstring).
        """
        self._load_consoles()
        self._refresh_results()

    def _load_consoles(self) -> None:
        consoles = console_service.list_consoles()
        self._console_names = self._populate_console_selector(consoles)
        self._filter_bar.set_available_consoles(consoles)

    def _refresh_results(self) -> None:
        """Cache-only (UI.md §5: must feel instant) — re-queries games for the
        current filters and hands the results to the table model.
        """
        account = self.app_context.active_account
        if account is None:
            self._current_results = []
            self._table_model.set_data([], self._console_names, set())
            self._results_count_label.setText("0 of 0 games")
            return

        base_filters = ExplorerFilters(search_text=self._search_input.text().strip() or None)
        filters = self._filter_bar.apply_to(base_filters)
        self._current_results = explorer_service.get_games(account.id, filters)
        total_count = explorer_service.get_total_game_count()
        installed_game_ids = library_service.get_installed_game_ids()

        self._table_model.set_data(self._current_results, self._console_names, installed_game_ids)
        self._results_count_label.setText(f"{len(self._current_results)} of {total_count} games")

    def _populate_console_selector(self, consoles: list[Console]) -> dict[int, str]:
        """Refills the sync-target console dropdown; returns an id -> name map for the table."""
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

    def _on_random(self) -> None:
        if not self._current_results:
            QMessageBox.information(self, "Random", "No games match the current filters.")
            return

        chosen = random.choice(self._current_results)
        self._select_game(chosen.game.id)

    def _select_game(self, game_id: int) -> None:
        for row, result in enumerate(self._current_results):
            if result.game.id == game_id:
                source_index = self._table_model.index(row, COLUMN_TITLE)
                proxy_index = self._proxy_model.mapFromSource(source_index)
                self._table.selectRow(proxy_index.row())
                self._table.scrollTo(proxy_index)
                return

    def _on_list_action(self, game_id: int, list_type: ListType) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        lists_service.add_to_list(account.id, game_id, list_type)
        # Blocking (and, less visibly, the other list actions) can change
        # whether this game still belongs in the current filtered/sorted
        # result set — re-query immediately rather than waiting for the
        # next unrelated refresh (a sync, a filter change) to catch up.
        self._refresh_results()

    def _on_follow(self, game_id: int) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        lists_service.add_to_list(account.id, game_id, ListType.FOLLOWING)
        self._refresh_results()

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
        self._load_consoles()

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
        self._refresh_results()

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
