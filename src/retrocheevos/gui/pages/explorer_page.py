"""Explorer page (UI.md 3.2) — "the heart of the app".

Layout matches RetroAchievements' own game list: a pill filter bar
(`widgets/explorer_filter_bar.py`) above a sortable data table, rather than
a collapsible side panel over a card grid. The table is a plain
`QTableView` + `QSortFilterProxyModel` over `gui/models/explorer_table_model.py`
— `QTableView` only ever paints *visible* rows via delegates
(`gui/delegates/explorer_delegates.py`), including the actions column
(Play/+), which is painted by `ActionsDelegate` rather than backed
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

from typing import Optional

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
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
from retrocheevos.services import (
    console_service,
    explorer_service,
    library_service,
    lists_service,
    session_service,
    sync_service,
)
from retrocheevos.widgets.explorer_filter_bar import ExplorerFilterBar

ROW_HEIGHT = 48


class ExplorerPage(Page):
    # Re-broadcast of the filter bar's own signal, for owning pages — see
    # `_on_filters_changed`.
    filters_changed = Signal()
    # Emitted after "Sync Everything" completes, carrying the ids of events
    # that appeared for the first time — Home turns those into notifications.
    sync_finished = Signal(list)

    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        # One worker attribute for both sync actions — they're mutually
        # exclusive (each disables both buttons for its duration), so the
        # two separate attributes this replaced only ever held one live
        # thread anyway.
        self._sync_worker: Optional[ServiceWorker] = None
        self._sync_phase = ""
        self._current_results: list[GameWithCompletion] = []
        self._console_names: dict[int, str] = {}
        self._image_loader = ImageLoader()

        # One button instead of the four this replaced (consoles, games for
        # console, full catalog, and the profile sync that used to live in
        # Settings): the first three were strictly nested — `sync_full_catalog`
        # already refreshes consoles and loops every one of them — and doing
        # them separately let the user run the profile sync before the
        # catalog, which silently drops completion data. See
        # `sync_service.sync_everything`.
        self._sync_everything_button = QPushButton("Sync Everything")
        self._sync_everything_button.setProperty("primary", True)
        self._sync_everything_button.setToolTip(
            "Update the game catalog, your profile and event progress from RetroAchievements."
        )
        self._sync_everything_button.clicked.connect(self._on_sync_everything)
        # Kept separate because it costs one API call per game (~1h for the
        # whole catalog vs ~3min for everything above), so it stays opt-in.
        # Resumable, so a second run is nearly instant.
        self._sync_median_times_button = QPushButton("Sync Median Times")
        self._sync_median_times_button.setToolTip(
            "Fetch median hardcore completion times for the catalog. Optional; may take a long time."
        )
        self._sync_median_times_button.clicked.connect(self._on_sync_median_times)

        # Same shape and the same reason as the button above: one request per
        # game, opt-in, resumable. This one is what makes ROM scanning able
        # to match files to games at all — `game_hashes` has no other writer.
        self._sync_hashes_button = QPushButton("Sync ROM Hashes")
        self._sync_hashes_button.setToolTip(
            "Fetch RetroAchievements ROM hashes to identify compatible ROMs and recheck unmatched files."
        )
        self._sync_hashes_button.clicked.connect(self._on_sync_game_hashes)

        self._catalog_sync_progress = QProgressBar()
        self._catalog_sync_progress.setVisible(False)
        self._catalog_sync_progress.setTextVisible(True)
        # Fixed percentage scale — see `_show_progress_percent` for why the
        # range isn't set per phase.
        self._catalog_sync_progress.setRange(0, 100)

        # Wrapped in a QWidget rather than added as a bare QHBoxLayout: a
        # QLayout has no setVisible(), and `set_results_visible` needs to
        # hide this whole strip as one unit when Home embeds this page.
        self._sync_bar_widget = QWidget()
        sync_bar = QHBoxLayout(self._sync_bar_widget)
        sync_bar.setContentsMargins(0, 0, 0, 0)
        sync_bar.addWidget(self._sync_everything_button)
        sync_bar.addWidget(self._sync_median_times_button)
        sync_bar.addWidget(self._sync_hashes_button)
        sync_bar.addWidget(self._catalog_sync_progress, stretch=1)
        sync_bar.addStretch(1)

        self._filter_bar = ExplorerFilterBar()
        self._filter_bar.filters_changed.connect(self._on_filters_changed)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search games...")
        self._search_input.returnPressed.connect(self._refresh_results)

        self._results_count_label = QLabel()

        # Same QWidget-wrapping reason as `_sync_bar_widget` above.
        self._search_row_widget = QWidget()
        search_row = QHBoxLayout(self._search_row_widget)
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.addWidget(self._search_input, stretch=1)
        search_row.addWidget(self._results_count_label)

        self._table_model = ExplorerTableModel(self._image_loader)
        self._proxy_model = QSortFilterProxyModel()
        self._proxy_model.setSourceModel(self._table_model)
        self._proxy_model.setSortRole(Qt.ItemDataRole.EditRole)

        self._table = QTableView()
        self._table.setModel(self._proxy_model)
        self._table.setItemDelegateForColumn(COLUMN_TITLE, TitleDelegate(self._table))
        self._table.setItemDelegateForColumn(COLUMN_PROGRESS, ProgressDelegate(self._table))
        self._actions_delegate = ActionsDelegate(self._table)
        self._actions_delegate.list_action_requested.connect(self._on_list_action)
        self._actions_delegate.block_requested.connect(self._on_block)
        self._actions_delegate.set_membership_provider(self._list_ids_for_game)
        self._table.setItemDelegateForColumn(COLUMN_ACTIONS, self._actions_delegate)
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
        layout.addWidget(self._sync_bar_widget)
        layout.addWidget(self._filter_bar)
        layout.addWidget(self._search_row_widget)
        layout.addWidget(self._table, stretch=1)

    def refresh(self) -> None:
        """Full refresh: reloads consoles (rarely change) and results. Called
        when the page becomes visible — filter/search changes call the
        lighter `_refresh_results()` instead (see module docstring).
        """
        self._load_consoles()
        self._refresh_list_options()
        self._refresh_results()

    def load_consoles(self) -> None:
        """Public wrapper so an owning page can populate the Console filter
        pill before any results are shown — Home keeps the filter bar
        visible while the results stay hidden, and an unpopulated pill would
        just read "All Consoles" with nothing to pick.
        """
        self._load_consoles()

    def set_results_visible(self, visible: bool) -> None:
        """Shows/hides the results area only.

        Home embeds this page with the filter pills AND the sync bar always
        on screen — syncing is a thing you go and do, not something that
        should require searching for a game first — while the results table
        and its search row appear once the user actually searches or filters.
        """
        self._search_row_widget.setVisible(visible)
        self._table.setVisible(visible)

    def set_search_text(self, text: str) -> None:
        """Lets an owning page (`gui/pages/home_page.py`'s embedded instance)
        drive this page's own search field and trigger results immediately —
        bypasses the `returnPressed`-only trigger this field normally uses
        when this page's own search box is typed into directly.
        """
        self._search_input.setText(text)
        self._refresh_results()

    def _on_filters_changed(self) -> None:
        self._refresh_results()
        # Re-emitted so an owning page can react (Home reveals the results
        # area when a pill is touched) without reaching into `_filter_bar`.
        self.filters_changed.emit()

    def _load_consoles(self) -> None:
        consoles = console_service.list_consoles()
        # Names for every console, including ones with no synced games — the
        # results table still has to label whatever rows it's given.
        self._console_names = {console.id: console.name for console in consoles}
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

    def _on_list_action(self, game_id: int, list_id: int) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        try:
            lists_service.add_to_list(account.id, game_id, list_id)
        except ValueError as error:
            QMessageBox.warning(self, "Can't add to list", str(error))
            return
        # Blocking (and, less visibly, the other list actions) can change
        # whether this game still belongs in the current filtered/sorted
        # result set — re-query immediately rather than waiting for the
        # next unrelated refresh (a sync, a filter change) to catch up.
        self._refresh_results()

    def _list_ids_for_game(self, game_id: int) -> set[int]:
        """Which lists this game is already in — ticks the "+" menu."""
        account = self.app_context.active_account
        if account is None:
            return set()
        return lists_service.get_list_ids_for_game(account.id, game_id)

    def _on_block(self, game_id: int) -> None:
        """Block resolves the list by slug, so it keeps working even if the
        user renames their Blocked list."""
        account = self.app_context.active_account
        if account is None:
            return
        blocked = next(
            (d for d in lists_service.list_definitions(account.id) if d.is_blocked), None
        )
        if blocked is None:
            return
        lists_service.add_to_list(account.id, game_id, blocked.id)
        self._refresh_results()

    def _refresh_list_options(self) -> None:
        """Keeps the "+" menu in step with the lists that actually exist —
        called from `refresh()`, so a list created on the Lists page shows up
        here on the next visit without a restart.
        """
        account = self.app_context.active_account
        if account is None:
            return
        options = [
            (definition.id, definition.name)
            for definition in lists_service.list_definitions(account.id)
            if definition.accepts_manual_membership and not definition.is_blocked
        ]
        self._actions_delegate.set_list_options(options)
        # Same set drives the filter bar's "Lists" pill — a list you can add
        # a game to is a list you can filter by.
        self._filter_bar.set_list_options(options)

    def _set_sync_buttons_enabled(self, enabled: bool) -> None:
        # Both share this — they both write to `games`, and running them
        # concurrently on separate threads would race each other's SQLite
        # writes for no benefit. It's also what makes a single worker
        # attribute safe (see `_sync_worker`).
        self._sync_everything_button.setEnabled(enabled)
        self._sync_median_times_button.setEnabled(enabled)
        self._sync_hashes_button.setEnabled(enabled)

    def _on_sync_failed(self, message: str) -> None:
        self._set_sync_buttons_enabled(True)
        self._catalog_sync_progress.setVisible(False)
        QMessageBox.warning(self, "Sync failed", message)

    def _on_sync_everything(self) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        client = session_service.build_api_client(account)
        self._set_sync_buttons_enabled(False)
        self._sync_phase = ""
        self._catalog_sync_progress.setRange(0, 0)  # indeterminate until the first phase reports
        self._catalog_sync_progress.setFormat("Starting sync…")
        self._catalog_sync_progress.setVisible(True)
        self._sync_worker = ServiceWorker(
            sync_service.sync_everything,
            client,
            account,
            report_progress=True,
            report_phase=True,
        )
        self._sync_worker.phase.connect(self._on_sync_phase)
        self._sync_worker.progress.connect(self._on_sync_progress)
        self._sync_worker.finished_ok.connect(self._on_sync_everything_done)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sync_phase(self, phase: str) -> None:
        self._sync_phase = phase
        self._catalog_sync_progress.setValue(0)
        self._catalog_sync_progress.setFormat(f"{phase}…")

    def _show_progress_percent(self, label: str, current: int, total: int) -> None:
        """Drives the bar on a fixed 0-100 scale.

        Deliberately not `setRange(0, total)`: `total` changes between phases
        (consoles, then games), so a per-phase range made the bar jump
        backwards and sit visually full at the end of each phase. A fixed
        percentage scale fills once, left to right, whatever the phase.
        """
        percent = int(current / total * 100) if total else 100
        self._catalog_sync_progress.setValue(percent)
        self._catalog_sync_progress.setFormat(f"{label} {current}/{total} — {percent}%")

    def _on_sync_progress(self, current: int, total: int) -> None:
        self._show_progress_percent(self._sync_phase, current, total)

    def _on_sync_everything_done(self, new_event_ids: object) -> None:
        self._set_sync_buttons_enabled(True)
        self._catalog_sync_progress.setVisible(False)
        self._load_consoles()
        self._refresh_results()
        self.sync_finished.emit(list(new_event_ids or []))

    def _on_sync_game_hashes(self) -> None:
        account = self.app_context.active_account
        if account is None:
            return

        # The times here are measured against the live API, not computed from
        # the pacing constant — the previous wording costed a request at the
        # 0.3s sleep alone, ignored the round trip on top of it, and so
        # advertised "about an hour" for a run that takes closer to 1h40.
        # Understating the cheap option is bad; understating the expensive
        # one at "three hours" when it is four, in a Yes/No where the
        # expensive answer buys nothing this feature uses, is worse.
        with_details = QMessageBox.question(
            self,
            "Sync ROM hashes",
            "Fetch ROM hashes for the whole catalog so scanned files match "
            "themselves to games.\n\n"
            "One request per game. Consoles you have ROMs for are fetched "
            "first — about 45 minutes — and the rest of the catalogue takes "
            "the run to roughly 1h40. You can stop once your own consoles "
            "are done: a second run only fetches what's still missing.\n\n"
            "Also fetch achievements and median times for every game? That "
            "is three requests per game instead of one, taking the whole "
            "catalogue to about 4 hours. Neither is used for ROM matching — "
            "answer No unless you specifically want that extra data.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        client = session_service.build_api_client(account)
        self._set_sync_buttons_enabled(False)
        self._catalog_sync_progress.setValue(0)
        self._catalog_sync_progress.setFormat("Starting hash sync…")
        self._catalog_sync_progress.setVisible(True)
        self._sync_worker = ServiceWorker(
            sync_service.sync_all_game_hashes,
            client,
            report_progress=True,
            full_details=with_details == QMessageBox.StandardButton.Yes,
        )
        self._sync_worker.progress.connect(self._on_game_hashes_progress)
        self._sync_worker.finished_ok.connect(self._on_game_hashes_done)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_game_hashes_progress(self, current: int, total: int) -> None:
        self._show_progress_percent("ROM hashes", current, total)

    def _on_game_hashes_done(self, synced: int) -> None:
        self._set_sync_buttons_enabled(True)
        self._catalog_sync_progress.setVisible(False)
        self.refresh()
        QMessageBox.information(
            self,
            "ROM hashes synced",
            f"{synced} game(s) now have ROM hashes.\n\n"
            "Previously unmatched ROMs were re-checked against them — see the "
            "Library for what matched.",
        )

    def _on_sync_median_times(self) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        client = session_service.build_api_client(account)
        self._set_sync_buttons_enabled(False)
        self._catalog_sync_progress.setValue(0)
        self._catalog_sync_progress.setFormat("Starting median time sync…")
        self._catalog_sync_progress.setVisible(True)
        self._sync_worker = ServiceWorker(
            sync_service.sync_median_times, client, report_progress=True
        )
        self._sync_worker.progress.connect(self._on_median_times_progress)
        self._sync_worker.finished_ok.connect(self._on_median_times_done)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_median_times_progress(self, current: int, total: int) -> None:
        self._show_progress_percent("Median time", current, total)

    def _on_median_times_done(self, filled: int) -> None:
        self._set_sync_buttons_enabled(True)
        self._catalog_sync_progress.setVisible(False)
        self._refresh_results()
        message = (
            f"{filled} more game(s) now have a median time to beat."
            if filled
            else "Every game already had whatever median time RetroAchievements publishes."
        )
        QMessageBox.information(self, "Median times synced", message)

