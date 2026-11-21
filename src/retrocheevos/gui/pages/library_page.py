"""Library page (R22) — the displayed account's local ROMs as a cover grid.

After the reviewed Library board: a header with the indexed-ROM count, a
Folders… dialog (the shared `RomFolderEditor`) and a Scan menu; local search,
All / In progress / Mastered / Unmatched (D9) and System filters; and a
model/view grid (`LibraryGridModel` + `LibraryCardDelegate`) whose covers load
only for painted cards within the R07 artwork budget.

Scans never move, rename or delete files: they only index what is already on
disk (`rom_folders` per console). Unmatched ROMs are cards like any other,
with Match to game…, Choose cover… and Remove in their context menu.
"""

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QListView, QMenu,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from retrocheevos.core.library_filter import (
    STATUS_ALL, STATUS_IN_PROGRESS, STATUS_MASTERED, STATUS_UNMATCHED, filter_entries,
)
from retrocheevos.gui import styles
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.components import FilterChip, SearchField, button, page_title, text_label
from retrocheevos.gui.delegates.library_card_delegate import (
    CELL_HEIGHT, MIN_CARD_WIDTH, LibraryCardDelegate,
)
from retrocheevos.gui.dialogs.folders_dialog import FoldersDialog
from retrocheevos.gui.flow_layout import FlowLayout
from retrocheevos.gui.dialogs.match_rom_dialog import MatchRomDialog
from retrocheevos.gui.models.library_grid_model import EntryRole, LibraryGridModel
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.view_state import restore_scroll_later
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.library.local_covers import cached_local_cover_path
from retrocheevos.models.library import LibraryEntry, RehashResult, RomFolderScanResult
from retrocheevos.services import console_service, library_service

SCAN_BUTTON_TEXT = "Scan"
SCANNING_TEXT = "Scanning…"
REHASH_ACTION_TEXT = "Verify hashes (re-hash library)"
SCAN_ALL_ACTION_TEXT = "Scan all folders"
SCAN_FILE_ACTION_TEXT = "Scan a ROM file…"
IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
FOOTER_NOTE = "Scanning indexes existing files. It does not move or download ROMs."
NO_ACCOUNT_TEXT = "Choose an account in the sidebar to see its library."
EMPTY_LIBRARY_TEXT = "No ROMs indexed yet. Add the folders where your ROMs are, then scan them."
NO_MATCH_TEXT = "No local games match."
ALL_MATCHED_TEXT = "All local ROMs are matched."
UNMATCHED_HINT = (
    "These files' hashes are not in the synced RetroAchievements catalog. Usually the "
    "console's hashes have not been synced yet: run Sync ROM Hashes from Home → Explore "
    "catalog, then Scan → Verify hashes. Hacks, translations and other dumps may never "
    "match; right-click a card and choose Match to game… to pick the game yourself."
)
CHANGE_MATCH_TEXT = "Change match…"
AUTOMATIC_MATCH_TEXT = "Use automatic match"
WORKER_SCAN = ("library", "scan")
WORKER_REHASH = ("library", "rehash")
WORKER_PLAY = ("library", "play")
MIN_COLUMNS = 2
SEARCH_WIDTH = 300

FILTERS = (
    (STATUS_ALL, "All"),
    (STATUS_IN_PROGRESS, "In progress"),
    (STATUS_MASTERED, "Mastered"),
    (STATUS_UNMATCHED, "Unmatched"),
)


class LibraryPage(Page):
    # Console id; MainWindow opens Settings' emulator editor on it.
    configure_emulator_requested = Signal(int)

    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._image_loader = app_context.create_image_loader()
        self._entries: list[LibraryEntry] = []
        self._status = STATUS_ALL
        self._console_filter: Optional[int] = None
        self._shown_account_id: Optional[int] = None
        self._last_result_details = ""
        self._console_names: dict[int, str] = {}
        self._cover_games: dict = {}

        # Header -------------------------------------------------------------
        self._count_label = text_label("", "secondary")
        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(page_title("Library"))
        heading.addWidget(self._count_label)
        folders_button = button("Folders…")
        folders_button.setToolTip("Add, remove and scan ROM folders")
        folders_button.clicked.connect(self.open_folders)
        self._scan_button = button(SCAN_BUTTON_TEXT)
        scan_menu = QMenu(self._scan_button)
        self._scan_all_action = scan_menu.addAction(SCAN_ALL_ACTION_TEXT, self._on_scan_all_folders)
        self._rehash_action = scan_menu.addAction(REHASH_ACTION_TEXT, self._on_rehash)
        self._rehash_action.setToolTip(
            "Recompute every indexed ROM's hash with the current hasher and re-match. "
            "Use after installing RAHasher or updating the app."
        )
        scan_menu.addSeparator()
        scan_menu.addAction(SCAN_FILE_ACTION_TEXT, self.open_folders)
        self._scan_button.setMenu(scan_menu)
        header = QHBoxLayout()
        header.addLayout(heading)
        header.addStretch(1)
        header.addWidget(folders_button)
        header.addWidget(self._scan_button)

        # Status row: progress / result, Cancel, Details ----------------------
        self._scan_status_label = text_label("", "secondary", wrap=True)
        self._scan_status_label.setVisible(False)
        self._cancel_button = button("Cancel", compact=True)
        self._cancel_button.clicked.connect(self._on_cancel_scan)
        self._cancel_button.setVisible(False)
        self._details_button = button("Details…", "ghost", compact=True)
        self._details_button.clicked.connect(self._show_result_details)
        self._details_button.setVisible(False)
        status_row = QHBoxLayout()
        status_row.addWidget(self._scan_status_label, stretch=1)
        status_row.addWidget(self._details_button)
        status_row.addWidget(self._cancel_button)

        # Toolbar --------------------------------------------------------------
        self._search = SearchField("Search local games")
        self._search.setFixedWidth(SEARCH_WIDTH)
        self._search.textChanged.connect(self._apply_filters)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_chips: dict[str, FilterChip] = {}
        # Wraps onto a second row in narrow windows instead of squeezing the
        # search field or clipping the chips.
        toolbar_widget = QWidget()
        toolbar_widget.setProperty("transparent", True)
        toolbar = FlowLayout(toolbar_widget, spacing=styles.SPACE_S)
        toolbar.addWidget(self._search)
        for status, label in FILTERS:
            chip = FilterChip(label, checked=status == STATUS_ALL)
            chip.clicked.connect(lambda _checked=False, s=status: self._set_status(s))
            self._filter_group.addButton(chip)
            self._filter_chips[status] = chip
            toolbar.addWidget(chip)
        self._system_filter = QComboBox()
        self._system_filter.setAccessibleName("System")
        self._system_filter.setMinimumWidth(180)
        self._system_filter.currentIndexChanged.connect(self._on_system_changed)
        toolbar.addWidget(self._system_filter)

        # Grid ------------------------------------------------------------------
        self._model = LibraryGridModel(self._image_loader, self)
        self._delegate = LibraryCardDelegate(self)
        self._delegate.play_requested.connect(self._on_play_index)
        self._grid = QListView()
        self._grid.setModel(self._model)
        self._grid.setItemDelegate(self._delegate)
        self._grid.setViewMode(QListView.ViewMode.IconMode)
        self._grid.setMovement(QListView.Movement.Static)
        self._grid.setResizeMode(QListView.ResizeMode.Adjust)
        self._grid.setUniformItemSizes(True)
        self._grid.setWrapping(True)
        self._grid.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._grid.setMouseTracking(True)
        self._grid.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        # Always shown: with "as needed", a row that only just fits made the
        # bar appear, which narrowed the viewport, which re-sized the cells,
        # which hid the bar again — the last card flickered between rows.
        self._grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._grid.verticalScrollBar().setSingleStep(24)
        self._grid.setAccessibleName("Local games")
        self._grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._grid.customContextMenuRequested.connect(self._on_context_menu)
        self._grid.activated.connect(self._on_play_index)
        self._grid.setProperty("libraryGrid", True)
        # The viewport, not the page, decides the columns: it narrows when the
        # scroll bar appears without the page itself resizing.
        self._grid.viewport().installEventFilter(self)

        self._unmatched_hint = text_label(UNMATCHED_HINT, "secondary", wrap=True)
        self._unmatched_hint.setVisible(False)
        self._message = text_label("", "secondary", wrap=True)
        self._add_folder_button = button("Add a folder…", "primary")
        self._add_folder_button.clicked.connect(self.open_folders)
        message_page = QWidget()
        message_layout = QVBoxLayout(message_page)
        message_layout.addWidget(self._message)
        message_layout.addWidget(self._add_folder_button, alignment=Qt.AlignmentFlag.AlignLeft)
        message_layout.addStretch(1)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._grid)
        self._stack.addWidget(message_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            styles.PAGE_PADDING_H, styles.PAGE_PADDING_V - 8,
            styles.PAGE_PADDING_H, styles.PAGE_PADDING_V - 12,
        )
        layout.setSpacing(styles.SPACE_M)
        layout.addLayout(header)
        layout.addLayout(status_row)
        layout.addWidget(toolbar_widget)
        layout.addWidget(self._unmatched_hint)
        layout.addWidget(self._stack, stretch=1)
        layout.addWidget(text_label(FOOTER_NOTE, "secondary", wrap=True))

    # Refresh and filters ----------------------------------------------------

    def refresh(self) -> None:
        account = self.app_context.active_account
        account_id = account.id if account is not None else None
        same_account = account_id == self._shown_account_id
        self._shown_account_id = account_id
        scroll = self._grid.verticalScrollBar().value()
        if not same_account:
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
            self._status = STATUS_ALL
            self._filter_chips[STATUS_ALL].setChecked(True)
            self._console_filter = None
        if account is None:
            self._entries = []
        else:
            # Entries recorded before `_is_not_a_rom` existed, and files
            # deleted outside the app: nothing else notices either.
            library_service.purge_non_rom_entries()
            library_service.purge_missing_roms()
            self._entries = library_service.list_library_entries()
        self._console_names = {c.id: c.name for c in console_service.list_consoles()}
        self._cover_games = (
            library_service.guess_games_for_unmatched_roms()
            if any(entry.kind == "rom" for entry in self._entries) else {}
        )
        self._reload_system_filter()
        rom_count = sum(len(entry.file_paths) for entry in self._entries)
        if account is None:
            self._count_label.setText("No account selected")
        elif rom_count:
            self._count_label.setText(f"{rom_count:,} local {'ROM' if rom_count == 1 else 'ROMs'} indexed")
        else:
            self._count_label.setText("No ROMs indexed yet")
        self._apply_filters()
        if same_account:
            restore_scroll_later(self._grid, scroll)

    def _reload_system_filter(self) -> None:
        present = sorted(
            {entry.console_id for entry in self._entries},
            key=lambda cid: self._console_names.get(cid, "").casefold(),
        )
        self._system_filter.blockSignals(True)
        self._system_filter.clear()
        self._system_filter.addItem("All systems", None)
        for console_id in present:
            self._system_filter.addItem(self._console_names.get(console_id, f"Console #{console_id}"), console_id)
        index = self._system_filter.findData(self._console_filter)
        if index < 0:
            self._console_filter = None
            index = 0
        self._system_filter.setCurrentIndex(index)
        self._system_filter.blockSignals(False)

    def _set_status(self, status: str) -> None:
        self._status = status
        self._filter_chips[status].setChecked(True)
        self._apply_filters()

    def _on_system_changed(self, _index: int) -> None:
        self._console_filter = self._system_filter.currentData()
        self._apply_filters()

    def _apply_filters(self) -> None:
        visible = filter_entries(self._entries, self._status, self._console_filter, self._search.text())
        self._model.set_entries(visible, self._console_names, self._cover_games)
        account = self.app_context.active_account
        self._add_folder_button.setVisible(False)
        self._unmatched_hint.setVisible(self._status == STATUS_UNMATCHED and bool(visible))
        if account is None:
            self._show_message(NO_ACCOUNT_TEXT)
        elif not self._entries:
            self._show_message(EMPTY_LIBRARY_TEXT)
            self._add_folder_button.setVisible(True)
        elif not visible:
            only_unmatched = (
                self._status == STATUS_UNMATCHED and not self._search.text().strip()
                and self._console_filter is None
            )
            self._show_message(ALL_MATCHED_TEXT if only_unmatched else NO_MATCH_TEXT)
        else:
            self._stack.setCurrentWidget(self._grid)

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentIndex(1)

    def message_text(self) -> Optional[str]:
        return self._message.text() if self._stack.currentIndex() == 1 else None

    def columns(self) -> int:
        return max(1, self._grid.viewport().width() // max(1, self._grid.gridSize().width()))

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 — Qt override
        if event.type() == QEvent.Type.Resize and watched is self._grid.viewport():
            self._update_grid_size()
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self._update_grid_size()

    def _update_grid_size(self) -> None:
        width = self._grid.viewport().width()
        if width <= 1:
            return
        columns = max(MIN_COLUMNS, width // MIN_CARD_WIDTH)
        # One pixel of slack per column: QListView wraps an item whose cell
        # would end exactly on the viewport edge.
        cell = QSize(width // columns - 1, CELL_HEIGHT)
        if cell != self._grid.gridSize():
            self._delegate.set_cell_size(cell)
            self._grid.setGridSize(cell)

    # Play -------------------------------------------------------------------

    def _on_play_index(self, index: QModelIndex) -> None:
        entry = index.data(EntryRole)
        if entry is not None:
            self.play_entry(entry)

    def play_entry(self, entry: LibraryEntry) -> None:
        """Guarded launch: missing files and missing emulators get next steps."""
        if entry.file_paths and not any(Path(path).exists() for path in entry.file_paths):
            answer = QMessageBox.question(
                self, "File not found",
                f"{entry.title} is no longer at:\n{entry.file_paths[0]}\n\n"
                "Remove it from the Library? The folder can be scanned again later.",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._remove_entry(entry)
            return
        if not entry.has_emulator:
            answer = QMessageBox.question(
                self, "No emulator configured",
                f"No emulator is set up for {self._model.console_name(entry.console_id)}. "
                "Configure one in Settings now?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.configure_emulator_requested.emit(entry.console_id)
            return
        if entry.kind == "game":
            worker = ServiceWorker(library_service.launch_game, entry.game.id)
        else:
            worker = ServiceWorker(library_service.launch_installed_rom, entry.rom.id)
        worker.failed.connect(self._on_play_failed)
        self.app_context.workers.start(worker, key=WORKER_PLAY)

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)

    # Context menu -----------------------------------------------------------

    def build_context_menu(self, entry: LibraryEntry) -> QMenu:
        menu = QMenu(self)
        play = menu.addAction("Play", lambda: self.play_entry(entry))
        play.setEnabled(entry.has_emulator)
        if entry.kind == "rom":
            menu.addAction("Match to game…", lambda: self.match_entry(entry))
            menu.addAction("Choose cover…", lambda: self._choose_cover(entry))
        else:
            menu.addAction(CHANGE_MATCH_TEXT, lambda: self.match_entry(entry))
            if entry.manual_roms:
                menu.addAction(AUTOMATIC_MATCH_TEXT, lambda: self.use_automatic_match(entry))
        menu.addAction("Configure emulator", lambda: self.configure_emulator_requested.emit(entry.console_id))
        menu.addSeparator()
        menu.addAction("Remove from Library", lambda: self._remove_entry(entry))
        return menu

    def _on_context_menu(self, position: QPoint) -> None:
        index = self._grid.indexAt(position)
        entry = index.data(EntryRole) if index.isValid() else None
        if entry is not None:
            self.build_context_menu(entry).popup(self._grid.viewport().mapToGlobal(position))

    def _remove_entry(self, entry: LibraryEntry) -> None:
        """Removes the index records only; files on disk are never touched."""
        if entry.kind == "game":
            library_service.remove_installed_roms_for_game(entry.game.id)
        else:
            library_service.remove_installed_rom(entry.rom.id)
        self.refresh()

    def _choose_cover(self, entry: LibraryEntry) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Select Cover Image", filter=IMAGE_FILE_FILTER)
        if not source:
            return
        pixmap = QPixmap(source)
        if pixmap.isNull():
            QMessageBox.warning(self, "Invalid image", "Couldn't read that file as an image.")
            return
        destination = cached_local_cover_path(entry.rom.id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(destination), "PNG")
        self._model.forget_cover(entry.key)

    def _choose_copy(self, entry: LibraryEntry):
        """The local file to re-match: asked only when a game has several."""
        if len(entry.roms) <= 1:
            return entry.roms[0] if entry.roms else entry.rom
        names = [Path(rom.file_path).name for rom in entry.roms]
        name, accepted = QInputDialog.getItem(
            self, CHANGE_MATCH_TEXT, f"{entry.title} has several local files. Which one?",
            names, 0, False,
        )
        return entry.roms[names.index(name)] if accepted else None

    def match_entry(self, entry: LibraryEntry) -> None:
        """Pick the game by hand: "Match to game…" for an unmatched ROM,
        "Change match…" when automatic matching chose the wrong game. The
        choice is kept as a manual match that later scans do not overwrite."""
        rom = self._choose_copy(entry)
        if rom is None:
            return
        console_name = self._model.console_name(rom.console_id)
        games = library_service.list_games_for_matching(rom.console_id)
        if not games:
            QMessageBox.information(
                self, "No games to match",
                f"No {console_name} games are synced locally yet. Sync the catalog "
                "from Home's Explore catalog first.",
            )
            return
        dialog = MatchRomDialog(rom.file_path, console_name, games, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        game_id = dialog.selected_game_id()
        if game_id is None or game_id == rom.game_id:
            return
        library_service.match_installed_rom_to_game(rom.id, game_id)
        self._model.forget_cover(entry.key)
        self.refresh()

    def use_automatic_match(self, entry: LibraryEntry) -> None:
        """Drop manual choices: each copy goes back to its hash's match."""
        results = [library_service.use_automatic_match(rom.id) for rom in entry.manual_roms]
        self._model.forget_cover(entry.key)
        if any(game_id is None for game_id in results):
            self._set_status_text(
                f"{entry.title}: the file's hash has no catalog match, so it is in Unmatched now."
            )
        else:
            self._set_status_text(f"{entry.title}: back to the automatic match.")
        self.refresh()

    # Folders and scans --------------------------------------------------------

    def open_folders(self) -> None:
        dialog = FoldersDialog(self)
        dialog.exec()
        if dialog.scan_folder_id is not None:
            self.start_folder_scan(dialog.scan_folder_id)
        elif dialog.scan_file is not None:
            console_id, path = dialog.scan_file
            library_service.scan_and_record_rom(path, console_id)
            self.refresh()
        else:
            self.refresh()

    def _set_status_text(self, text: str) -> None:
        self._scan_status_label.setText(text)
        self._scan_status_label.setVisible(bool(text))

    def _on_scan_progress(self, discovered: int, path: str) -> None:
        # Sets the label directly (not via `_set_status_text`): it runs for
        # every progress tick and is exercised on its own by tests.
        self._scan_status_label.setText(f"Discovered {discovered} entries — {path}")
        self._scan_status_label.setVisible(True)

    def _acquire(self, job: str):
        from retrocheevos.services.job_coordinator import active_job, try_acquire

        token = try_acquire(job)
        if token is None:
            QMessageBox.warning(self, "Busy", f"Cannot start: {active_job()} is already running.")
        return token

    def _begin_job(self) -> None:
        self._set_scan_buttons_enabled(False)
        self._scan_button.setText(SCANNING_TEXT)
        self._set_status_text("")
        self._details_button.setVisible(False)
        self._cancel_button.setVisible(True)

    def start_folder_scan(self, folder_id: int) -> None:
        from retrocheevos.services.job_coordinator import JOB_SCAN_FOLDER

        token = self._acquire(JOB_SCAN_FOLDER)
        if token is None:
            return
        self._begin_job()
        worker = ServiceWorker(
            library_service.scan_rom_folder, folder_id, report_scan_progress=True, cancellable=True,
        )
        self._connect_scan(worker, token)

    def _on_scan_all_folders(self) -> None:
        from retrocheevos.services.job_coordinator import JOB_SCAN_ALL_FOLDERS

        if not library_service.list_rom_folders():
            QMessageBox.information(self, "No ROM folders", "Add a folder for a console first.")
            self.open_folders()
            return
        token = self._acquire(JOB_SCAN_ALL_FOLDERS)
        if token is None:
            return
        self._begin_job()
        worker = ServiceWorker(library_service.scan_all_rom_folders, report_scan_progress=True, cancellable=True)
        self._connect_scan(worker, token)

    def _connect_scan(self, worker: ServiceWorker, token) -> None:
        worker.scan_progress.connect(self._on_scan_progress)
        worker.finished_ok.connect(lambda result: (self._on_scan_done(result), self._release_job(token)))
        worker.failed.connect(lambda message: (self._on_scan_failed(message), self._release_job(token)))
        worker.cancelled.connect(lambda: (self._on_job_cancelled(), self._release_job(token)))
        self.app_context.workers.start(worker, key=WORKER_SCAN)

    def _on_rehash(self) -> None:
        from retrocheevos.services.job_coordinator import JOB_REHASH_LIBRARY

        if not self._entries:
            QMessageBox.information(self, "Nothing to re-hash", "No ROMs have been scanned yet.")
            return
        token = self._acquire(JOB_REHASH_LIBRARY)
        if token is None:
            return
        self._begin_job()
        self._set_status_text("Verifying hashes…")
        worker = ServiceWorker(library_service.rehash_installed_roms, cancellable=True)
        worker.finished_ok.connect(lambda result: (self._on_rehash_done(result), self._release_job(token)))
        worker.failed.connect(lambda message: (self._on_rehash_failed(message), self._release_job(token)))
        worker.cancelled.connect(lambda: (self._on_job_cancelled(), self._release_job(token)))
        self.app_context.workers.start(worker, key=WORKER_REHASH)

    def _on_cancel_scan(self) -> None:
        self._cancel_button.setEnabled(False)
        self._set_status_text("Cancelling…")
        self.app_context.workers.cancel_key(WORKER_SCAN)
        self.app_context.workers.cancel_key(WORKER_REHASH)

    def _on_job_cancelled(self) -> None:
        self._reset_scan_button()
        self._set_status_text("Cancelled. Files indexed so far are kept.")

    def _reset_scan_button(self) -> None:
        self._scan_button.setText(SCAN_BUTTON_TEXT)
        self._set_scan_buttons_enabled(True)
        self._cancel_button.setVisible(False)
        self._cancel_button.setEnabled(True)

    def _set_scan_buttons_enabled(self, enabled: bool) -> None:
        # Scans and the re-hash write the same tables, so they exclude each other.
        self._scan_button.setEnabled(enabled)
        self._scan_all_action.setEnabled(enabled)
        self._rehash_action.setEnabled(enabled)

    def _release_job(self, token) -> None:
        from retrocheevos.services.job_coordinator import release

        release(token)

    def _invalidate_artwork_for_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        normalized = {os.path.normcase(str(Path(p).expanduser().resolve())) for p in paths}
        for rom in library_service.list_installed_roms():
            if os.path.normcase(str(Path(rom.file_path).expanduser().resolve())) in normalized:
                if rom.id is not None:
                    self._image_loader.forget_rom(rom.id)
                    self._model.forget_cover(("rom", rom.id))
                    if rom.game_id is not None:
                        self._model.forget_cover(("game", rom.game_id))

    def _on_scan_done(self, result: RomFolderScanResult) -> None:
        # In-flight artwork for changed files must not repaint old covers (R04).
        self._invalidate_artwork_for_paths(
            list(result.changed_paths) + list(result.preserved_manual_matches)
        )
        self._reset_scan_button()
        self._show_result(_describe_scan(result), _scan_details(result))
        self.refresh()

    def _on_scan_failed(self, message: str) -> None:
        self._reset_scan_button()
        self._set_status_text("")
        QMessageBox.warning(self, "Folder scan failed", message)

    def _on_rehash_done(self, result: RehashResult) -> None:
        self._invalidate_artwork_for_paths(list(result.changed_paths))
        self._reset_scan_button()
        self._show_result(_describe_rehash(result), _rehash_details(result))
        self.refresh()

    def _on_rehash_failed(self, message: str) -> None:
        self._reset_scan_button()
        self._set_status_text("")
        QMessageBox.warning(self, "Re-hash failed", message)

    def _show_result(self, summary: str, details: str) -> None:
        self._set_status_text(summary)
        self._last_result_details = details
        self._details_button.setVisible(bool(details))

    def _show_result_details(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Scan details")
        box.setText(self._scan_status_label.text())
        box.setDetailedText(self._last_result_details)
        box.exec()


def _section(title: str, paths) -> str:
    paths = list(paths)
    if not paths:
        return ""
    return f"{title} ({len(paths)}):\n" + "\n".join(f"  {path}" for path in paths) + "\n\n"


def _scan_details(result: RomFolderScanResult) -> str:
    return (
        _section("Ambiguous — console unclear; add the file's console folder or scan it as a single file",
                 result.ambiguous_paths)
        + _section("Unsupported or unrecognized", result.unrecognized_paths)
        + _section("Could not be read", result.failed_paths)
        + _section("Folders that could not be scanned", result.failed_folders)
        + _section("Changed and re-hashed", result.changed_paths)
        + _section("Manual matches preserved", result.preserved_manual_matches)
    ).strip()


def _rehash_details(result: RehashResult) -> str:
    return (
        _section("Missing files", result.missing)
        + _section("Failed to hash", result.failed)
        + _section("Manual matches preserved for review", result.manual_matches_preserved)
    ).strip()


def _describe_scan(result: RomFolderScanResult) -> str:
    """One line summarising the scan. The skipped counts are reported rather
    than hidden: a folder that comes back "0 new ROMs" is otherwise
    indistinguishable from one where every file was ambiguous.
    """
    parts = [f"{len(result.recorded)} new ROM(s) found"]
    unmatched = sum(rom.game_id is None for rom in result.recorded)
    if unmatched:
        parts.append(f"{unmatched} available in Library, not yet matched to a catalog game")
    if result.already_known_count:
        parts.append(f"{result.already_known_count} already known")
    if result.ambiguous_paths:
        parts.append(f"{len(result.ambiguous_paths)} ambiguous (console unclear)")
    if result.unrecognized_paths:
        parts.append(f"{len(result.unrecognized_paths)} unsupported/unrecognized file(s)")
    if result.failed_paths:
        parts.append(f"{len(result.failed_paths)} file(s) could not be read")
    if result.failed_folders:
        parts.append(f"{len(result.failed_folders)} folder(s) could not be scanned")
    if result.changed_paths:
        parts.append(f"{len(result.changed_paths)} changed file(s) re-hashed")
    if result.preserved_manual_matches:
        parts.append(f"{len(result.preserved_manual_matches)} manual match(es) preserved")
    return ", ".join(parts) + "."


def _describe_rehash(result: RehashResult) -> str:
    """One line summarising the re-hash pass.

    "0 changed" is the expected result on a second run and says something
    useful — the library is already on the current hasher — so it is stated
    rather than left as an empty-looking success.
    """
    parts = [f"{result.checked} ROM(s) checked", f"{result.changed} hash(es) updated"]
    if result.newly_matched:
        parts.append(f"{result.newly_matched} newly matched")
    if result.missing:
        parts.append(f"{len(result.missing)} file(s) missing")
    if result.failed:
        parts.append(f"{len(result.failed)} failed to hash")
    if result.manual_matches_preserved:
        parts.append(f"{len(result.manual_matches_preserved)} manual match(es) preserved for review")
    return ", ".join(parts) + "."
