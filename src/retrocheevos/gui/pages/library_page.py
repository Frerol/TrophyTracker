"""Library page (UI.md 3.3/3.6) — what you have installed, and where it lives.

Its own page, reached from Home's user menu. It briefly lived as a "list"
inside the Lists page and never fitted: it stores no rows (membership is
whatever `installed_roms` says right now), it takes no manual additions, and
it renders a cover-art grid nothing else uses. Being in that dropdown just
meant a selector entry that behaved unlike every other entry.

Two halves, both inherited from the deleted ROM Location page:

- **the grid** — every installed game with a matched ROM, as clickable cover
  art (`InstalledGameFrame`); clicking the art launches it.
- **the folder section** — ROM folders per console, the scan that fills the
  grid, and the unmatched-ROM fallback for files hashing couldn't resolve.

The folder section reuses `rom_folders` (which already has a `console_id`
column) rather than the `rom_destinations` table Bloco 11 removed: two
tables both meaning "where this console's ROMs live" would drift apart.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.delegates.removable_list_delegate import RemovableListDelegate
from retrocheevos.gui.dialogs.match_rom_dialog import MatchRomDialog
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.selection import selected_item
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.library import RehashResult, RomFolderScanResult
from retrocheevos.services import console_service, library_service, preferences_service
from retrocheevos.widgets.cover_size_slider import CoverSizeSlider
from retrocheevos.widgets.console_selector import ConsoleSelector
from retrocheevos.widgets.installed_game_frame import InstalledGameFrame
from retrocheevos.widgets.unmatched_rom_card import UnmatchedRomCard

# Columns are derived from the cover size *and the real viewport width*, so
# the grid fills whatever screen it's on instead of stopping at a fixed
# number. It was a constant (`GRID_TARGET_WIDTH = 980`), which capped the row
# at 4 covers on a wide window and left the right-hand side empty.
MIN_GRID_COLUMNS = 2
# Frame border + layout margins + grid spacing around the cover, so the count
# is based on the space a card really occupies rather than the art alone.
CARD_PADDING = 24
# Scroll bar plus the scroll area's own frame — without allowing for it the
# last column lands half under the bar and the view scrolls horizontally.
# Vertical scrollbar (14px, `gui/styles.py`) plus the scroll area's 1px
# border each side. It was 28 — a guess with padding on top of padding, which
# cost a whole column at some sizes and left a wide empty strip on the right.
VIEWPORT_CHROME = 16

# Both `UserRole`, not `UserRole` and `UserRole + 1`: they live on *different*
# list widgets so there's no clash, and `RemovableListDelegate` reads
# `UserRole` specifically. Storing the ROM id one role higher is why its "−"
# silently removed nothing — the delegate emitted an empty role.
ROM_FOLDER_ID_ROLE = Qt.ItemDataRole.UserRole
ROM_ID_ROLE = Qt.ItemDataRole.UserRole

EMPTY_TEXT = "No installed games yet. Add a ROM folder below and scan it."
SCAN_BUTTON_TEXT = "Scan Folder"
SCAN_ALL_BUTTON_TEXT = "Scan All Folders"
REHASH_BUTTON_TEXT = "Re-hash Library"
REMOVE_BUTTON_WIDTH = 32
REFRESH_BUTTON_TEXT = "Refresh"

# The folder section is a tool, not the content. Left unbounded its two list
# widgets claim their full size hint and squeeze the cover grid — which is
# the point of the page — into a strip a row and a half tall.
FOLDER_LIST_MAX_HEIGHT = 110
UNMATCHED_LIST_MAX_HEIGHT = 90


class LibraryPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._play_worker: Optional[ServiceWorker] = None
        self._scan_worker: Optional[ServiceWorker] = None
        # One loader shared by every frame in the grid, same arrangement
        # Home uses for Continue Playing.
        self._image_loader = ImageLoader()

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setWidget(self._grid_container)
        scroll_area = self._scroll_area
        # Tracked so `resizeEvent` only rebuilds when the count actually
        # changes, not on every pixel of a window drag.
        self._last_grid_columns = 0

        self._cover_slider = CoverSizeSlider(
            initial_size=preferences_service.get_int(
                preferences_service.KEY_LIBRARY_COVER_SIZE, 150
            ),
            min_size=100,
            max_size=160,
        )
        self._cover_slider.size_changed.connect(self._on_cover_size_changed)

        # The page only rebuilt itself on navigation, so a ROM deleted from
        # disk (or added by another means) needed a trip to another section
        # and back before the grid caught up. `refresh()` is also what runs
        # the missing-file sweep, so this is the button that makes that
        # sweep reachable without leaving the page.
        refresh_button = QPushButton(REFRESH_BUTTON_TEXT)
        refresh_button.setToolTip("Re-read what's installed and drop anything gone")
        refresh_button.clicked.connect(self.refresh)

        slider_row = QHBoxLayout()
        slider_row.addWidget(self._cover_slider)
        slider_row.addWidget(refresh_button)
        slider_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(slider_row)
        layout.addWidget(scroll_area, stretch=1)
        layout.addWidget(self._build_rom_folders_section())

    def _build_rom_folders_section(self) -> QWidget:
        container = QWidget()

        self._folder_console_selector = ConsoleSelector()
        add_folder_button = QPushButton("Add Folder for Console...")
        add_folder_button.clicked.connect(self._on_add_rom_folder)
        remove_folder_button = QPushButton("Remove Selected")
        remove_folder_button.clicked.connect(self._on_remove_rom_folder)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder_console_selector, stretch=1)
        folder_row.addWidget(add_folder_button)
        folder_row.addWidget(remove_folder_button)

        self._rom_folders_list = QListWidget()
        self._rom_folders_list.setMaximumHeight(FOLDER_LIST_MAX_HEIGHT)

        self._scan_button = QPushButton(SCAN_BUTTON_TEXT)
        self._scan_button.clicked.connect(self._on_scan_folder)
        # Scans every configured folder, so it needs no selection — which is
        # the common case once more than one console is set up, and the one
        # the per-folder button made tedious.
        self._scan_all_button = QPushButton(SCAN_ALL_BUTTON_TEXT)
        self._scan_all_button.clicked.connect(self._on_scan_all_folders)
        # Neither scan button can reach an already-recorded ROM: both skip
        # files already in `installed_roms`, so a ROM keeps whatever hash the
        # app computed the day it was scanned. This is the only way to pick up
        # a hashing improvement without removing and re-adding every folder.
        self._rehash_button = QPushButton(REHASH_BUTTON_TEXT)
        self._rehash_button.setToolTip(
            "Recompute the hash of every ROM already in the library using the "
            "current hasher, then re-match. Use after installing RAHasher or "
            "updating the app. Only rewrites hashes that actually changed."
        )
        self._rehash_button.clicked.connect(self._on_rehash)
        self._scan_status_label = QLabel()
        scan_row = QHBoxLayout()
        scan_row.addWidget(self._scan_button)
        scan_row.addWidget(self._scan_all_button)
        scan_row.addWidget(self._rehash_button)
        scan_row.addWidget(self._scan_status_label, stretch=1)

        # Without this, a ROM whose hash matched nothing would be invisible
        # everywhere — it isn't in the grid above (that lists games with a
        # match), so there'd be no way left to tell the app what it is.
        self._unmatched_list = QListWidget()
        self._unmatched_list.setMaximumHeight(UNMATCHED_LIST_MAX_HEIGHT)
        # A "−" on **every row**, not one button acting on the selection.
        # Clearing out a handful of stragglers means clicking each one; with
        # a selection-based button that's select, click, select, click.
        # `RemovableListDelegate` is what Settings already uses for exactly
        # this shape of list.
        unmatched_delegate = RemovableListDelegate(self._unmatched_list)
        unmatched_delegate.remove_requested.connect(self._remove_unmatched)
        self._unmatched_list.setItemDelegate(unmatched_delegate)
        match_button = QPushButton("Match to Game...")
        match_button.clicked.connect(self._on_match_to_game)
        scan_file_button = QPushButton("Scan ROM File...")
        scan_file_button.clicked.connect(self._on_scan_file)
        # "−" rather than "Delete": it removes the entry from this list, it
        # does not touch the file. Same symbol and meaning as the one on the
        # Lists page's cards.
        remove_unmatched_button = QPushButton("−")
        remove_unmatched_button.setFixedWidth(REMOVE_BUTTON_WIDTH)
        remove_unmatched_button.setToolTip(
            "Remove from this list (the file on disk is left alone)"
        )
        remove_unmatched_button.clicked.connect(self._on_remove_unmatched)

        unmatched_row = QHBoxLayout()
        unmatched_row.addWidget(scan_file_button)
        unmatched_row.addWidget(match_button)
        unmatched_row.addWidget(remove_unmatched_button)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("ROM folders per console"))
        layout.addLayout(folder_row)
        layout.addWidget(self._rom_folders_list)
        layout.addLayout(scan_row)
        layout.addWidget(QLabel("Unmatched ROMs (hashing found no game)"))
        layout.addWidget(self._unmatched_list)
        layout.addLayout(unmatched_row)
        return container

    def refresh(self) -> None:
        # Re-read the stored size every time. The slider took its value at
        # construction, when there may have been no account signed in — so
        # without this, logging in showed the *default* size and the
        # account's saved one was never applied.
        self._cover_slider.set_value_silently(
            preferences_service.get_int(preferences_service.KEY_LIBRARY_COVER_SIZE, 150)
        )
        self._clear_grid()
        # Clears out entries recorded before `_is_not_a_rom` existed — saves,
        # box art and patches that a pre-filter scan had already written into
        # `installed_roms`. The filter is preventive only; without this they
        # stay under "Unmatched ROMs" forever. No-op once they're gone.
        library_service.purge_non_rom_entries()
        # Files deleted outside the app. Nothing else notices — `installed_roms`
        # is only written by a scan — so a ROM removed from disk stayed in the
        # Library indefinitely.
        library_service.purge_missing_roms()
        self._refresh_rom_folders()

        console_names = {console.id: console.name for console in console_service.list_consoles()}
        games = library_service.get_installed_games()
        # ROMs whose hash matched no game belong here too. They were only in
        # Home's Continue Playing before, which meant a folder scan could
        # report "12 new ROMs" and the Library — the page whose whole job is
        # showing what you have — would list eight of them. Anything scanned
        # appears here; the unmatched ones just can't show cover art or
        # progress, because nothing knows yet which game they are.
        unmatched = [
            rom for rom in library_service.list_installed_roms() if rom.game_id is None
        ]
        if not games and not unmatched:
            self._grid_layout.addWidget(QLabel(EMPTY_TEXT), 0, 0)
            return

        cover_size = self._cover_slider.value()
        # Cards are built before any are placed, so the column count can come
        # from their **measured** width. Estimating it as
        # `cover_size + a constant` was close but not always right — the
        # card's margins scale with the cover and the frame adds borders — so
        # at some sizes the last column overflowed and got clipped instead of
        # wrapping.
        cards: list[QWidget] = []
        for game in games:
            frame = InstalledGameFrame(
                game,
                self._image_loader,
                console_name=console_names.get(game.console_id),
                cover_size=cover_size,
            )
            frame.play_requested.connect(self._on_play)
            frame.remove_requested.connect(self._on_remove_game)
            cards.append(frame)

        # After the matched ones: these are the "needs attention" tail, and
        # the Match to Game… list below is where they get resolved.
        cover_guesses = library_service.guess_games_for_unmatched_roms()
        for rom in unmatched:
            card = UnmatchedRomCard(
                rom,
                console_name=console_names.get(rom.console_id),
                cover_game=cover_guesses.get(rom.id),
                image_loader=self._image_loader,
                cover_size=cover_size,
            )
            card.play_requested.connect(self._on_play_unmatched_rom)
            card.remove_requested.connect(self._remove_unmatched)
            cards.append(card)

        widest = max((card.sizeHint().width() for card in cards), default=cover_size)
        columns = self._columns_for_card_width(widest)
        self._last_grid_columns = columns
        for index, card in enumerate(cards):
            self._grid_layout.addWidget(
                card,
                index // columns,
                index % columns,
                alignment=Qt.AlignmentFlag.AlignHCenter,
            )
        # Whatever width is left after the last whole column gets shared out
        # between the columns instead of piling up on the right. The cards are
        # fixed-width, so without this the remainder — up to a full card's
        # worth — sat as one dead block at the end of every row.
        for column in range(columns):
            self._grid_layout.setColumnStretch(column, 1)

    def _on_cover_size_changed(self, size: int) -> None:
        preferences_service.set_int(preferences_service.KEY_LIBRARY_COVER_SIZE, size)
        self.refresh()

    def _columns_for_card_width(self, card_width: int) -> int:
        """Columns that fit, from a card's measured width — see `refresh`."""
        available = self._scroll_area.viewport().width()
        if available <= 1:
            available = self.width()
        spacing = max(0, self._grid_layout.horizontalSpacing())
        usable = max(0, available - VIEWPORT_CHROME)
        return max(MIN_GRID_COLUMNS, (usable + spacing) // (card_width + spacing))

    def _grid_columns(self, cover_size: int) -> int:
        """How many cards fit across the grid right now.

        Measured from the live viewport, not a constant — the page is used at
        whatever size the window happens to be, and a fixed target width
        meant a 4-wide row with dead space beside it on anything larger.
        Falls back to this page's own width before the scroll area has been
        laid out (first `refresh()` runs before the widget is shown, where
        the viewport still reports a placeholder size).
        """
        available = self._scroll_area.viewport().width()
        if available <= 1:
            available = self.width()
        usable = max(0, available - VIEWPORT_CHROME)
        return max(MIN_GRID_COLUMNS, usable // (cover_size + CARD_PADDING))

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Reflow once the page is actually on screen.

        `refresh()` is called by `MainWindow._show_page` *before* the widget
        is laid out, when the viewport still reports a placeholder width — so
        the first grid was built for a narrow page and kept that column count
        if no resize happened afterwards. That's the "only fills half the
        screen" case.
        """
        super().showEvent(event)
        columns = self._grid_columns(self._cover_slider.value())
        if columns != self._last_grid_columns:
            self._last_grid_columns = columns
            self.refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Reflow on resize so widening the window actually adds columns.

        Guarded on the column count rather than rebuilding on every pixel of
        a drag: a resize fires continuously, and the grid teardown/rebuild is
        far too expensive to run at that rate.
        """
        super().resizeEvent(event)
        columns = self._grid_columns(self._cover_slider.value())
        if columns != self._last_grid_columns:
            self._last_grid_columns = columns
            self.refresh()

    def _clear_grid(self) -> None:
        # Column stretches survive `takeAt`, so a wide layout followed by a
        # narrow one would keep phantom stretched columns to the right.
        for column in range(self._grid_layout.columnCount()):
            self._grid_layout.setColumnStretch(column, 0)
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_play(self, game_id: int) -> None:
        self._play_worker = ServiceWorker(library_service.launch_game, game_id)
        self._play_worker.failed.connect(self._on_play_failed)
        self._play_worker.start()

    def _on_play_unmatched_rom(self, installed_rom_id: int) -> None:
        """Launched by `installed_roms.id`, not `game_id` — there isn't one."""
        self._play_worker = ServiceWorker(
            library_service.launch_installed_rom, installed_rom_id
        )
        self._play_worker.failed.connect(self._on_play_failed)
        self._play_worker.start()

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)

    # --- ROM folders --------------------------------------------------

    def _refresh_rom_folders(self) -> None:
        consoles = console_service.list_configurable_consoles()
        console_names = {console.id: console.name for console in consoles}

        previous = self._folder_console_selector.currentData()
        self._folder_console_selector.clear()
        for console in consoles:
            self._folder_console_selector.addItem(console.name, console.id)
        if previous is not None:
            index = self._folder_console_selector.findData(previous)
            if index >= 0:
                self._folder_console_selector.setCurrentIndex(index)

        self._rom_folders_list.clear()
        for folder in library_service.list_rom_folders():
            console_label = (
                console_names.get(folder.console_id, f"Console #{folder.console_id}")
                if folder.console_id is not None
                else "Any console"
            )
            item = QListWidgetItem(f"{console_label}: {folder.path}")
            item.setData(ROM_FOLDER_ID_ROLE, folder.id)
            self._rom_folders_list.addItem(item)

        self._unmatched_list.clear()
        for rom in library_service.list_installed_roms():
            if rom.game_id is not None:
                continue
            console_label = console_names.get(rom.console_id, f"Console #{rom.console_id}")
            item = QListWidgetItem(f"{console_label}: {rom.file_path}")
            item.setData(ROM_ID_ROLE, rom.id)
            self._unmatched_list.addItem(item)

    def _on_add_rom_folder(self) -> None:
        console_id = self._folder_console_selector.currentData()
        if console_id is None:
            QMessageBox.warning(
                self, "No console selected", "Pick a console before adding its folder."
            )
            return
        path = QFileDialog.getExistingDirectory(self, "Select ROM Folder")
        if not path:
            return
        library_service.add_rom_folder(path, console_id=console_id)
        self._refresh_rom_folders()

    def _on_remove_rom_folder(self) -> None:
        item = selected_item(self._rom_folders_list)
        if item is None:
            QMessageBox.information(
                self, "No folder selected", "Pick a folder from the list above to remove."
            )
            return
        library_service.remove_rom_folder(item.data(ROM_FOLDER_ID_ROLE))
        self._refresh_rom_folders()

    def _on_scan_folder(self) -> None:
        item = selected_item(self._rom_folders_list)
        if item is None:
            QMessageBox.warning(
                self, "No folder selected", "Pick a folder from the list above to scan."
            )
            return

        self._set_scan_buttons_enabled(False)
        self._scan_button.setText("Scanning...")
        self._scan_status_label.setText("")
        self._scan_worker = ServiceWorker(
            library_service.scan_rom_folder, item.data(ROM_FOLDER_ID_ROLE)
        )
        self._scan_worker.finished_ok.connect(self._on_scan_done)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_all_folders(self) -> None:
        if self._rom_folders_list.count() == 0:
            QMessageBox.warning(
                self, "No ROM folders", "Add a folder for a console first."
            )
            return

        # Both buttons disabled: they write to the same tables, and letting a
        # single-folder scan start on top of the sweep would have two threads
        # hashing and inserting at once.
        self._set_scan_buttons_enabled(False)
        self._scan_all_button.setText("Scanning...")
        self._scan_status_label.setText("")
        self._scan_worker = ServiceWorker(library_service.scan_all_rom_folders)
        self._scan_worker.finished_ok.connect(self._on_scan_done)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_rehash(self) -> None:
        if self._unmatched_list.count() == 0 and self._rom_folders_list.count() == 0:
            QMessageBox.warning(
                self, "Nothing to re-hash", "No ROMs have been scanned yet."
            )
            return

        self._set_scan_buttons_enabled(False)
        self._rehash_button.setText("Re-hashing...")
        self._scan_status_label.setText("")
        self._rehash_worker = ServiceWorker(library_service.rehash_installed_roms)
        self._rehash_worker.finished_ok.connect(self._on_rehash_done)
        self._rehash_worker.failed.connect(self._on_rehash_failed)
        self._rehash_worker.start()

    def _on_rehash_done(self, result: RehashResult) -> None:
        self._reset_scan_button()
        self._scan_status_label.setText(_describe_rehash(result))
        self.refresh()

    def _on_rehash_failed(self, message: str) -> None:
        self._reset_scan_button()
        self._scan_status_label.setText("")
        QMessageBox.warning(self, "Re-hash failed", message)

    def _set_scan_buttons_enabled(self, enabled: bool) -> None:
        self._scan_button.setEnabled(enabled)
        self._scan_all_button.setEnabled(enabled)
        # Same tables as the scans, so it shares their mutual exclusion.
        self._rehash_button.setEnabled(enabled)

    def _reset_scan_button(self) -> None:
        self._scan_button.setText(SCAN_BUTTON_TEXT)
        self._scan_all_button.setText(SCAN_ALL_BUTTON_TEXT)
        self._rehash_button.setText(REHASH_BUTTON_TEXT)
        self._set_scan_buttons_enabled(True)

    def _on_scan_done(self, result: RomFolderScanResult) -> None:
        self._reset_scan_button()
        self._scan_status_label.setText(_describe_scan(result))
        self.refresh()

    def _on_scan_failed(self, message: str) -> None:
        self._reset_scan_button()
        self._scan_status_label.setText("")
        QMessageBox.warning(self, "Folder scan failed", message)

    def _on_scan_file(self) -> None:
        console_id = self._folder_console_selector.currentData()
        if console_id is None:
            QMessageBox.warning(
                self,
                "No console selected",
                "Pick a console above before scanning a single ROM file.",
            )
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Select ROM File")
        if not file_path:
            return
        library_service.scan_and_record_rom(file_path, console_id)
        self.refresh()

    def _on_remove_unmatched(self) -> None:
        item = selected_item(self._unmatched_list)
        if item is None:
            QMessageBox.information(
                self, "Nothing selected", "Pick a ROM from the list above to remove."
            )
            return
        self._remove_unmatched(item.data(ROM_ID_ROLE))

    def _on_remove_game(self, game_id: int) -> None:
        """Right-click → "Remove from Library" on a matched card. Drops every
        recorded copy of that game; the files stay on disk, and a rescan of
        the folder brings it back."""
        library_service.remove_installed_roms_for_game(game_id)
        self.refresh()

    def _remove_unmatched(self, installed_rom_id: int) -> None:
        """Removes the record, never the file — same contract as the "−" on
        the Lists page. A later scan can pick it up again."""
        library_service.remove_installed_rom(installed_rom_id)
        # Full refresh: the grid above lists unmatched ROMs too, so removing
        # one here has to take its card with it.
        self.refresh()

    def _on_match_to_game(self) -> None:
        item = selected_item(self._unmatched_list)
        if item is None:
            QMessageBox.information(
                self, "Nothing selected", "Pick a ROM from the list above to match."
            )
            return
        installed_rom = library_service.get_installed_rom(item.data(ROM_ID_ROLE))
        if installed_rom is None:
            return

        console_names = {console.id: console.name for console in console_service.list_consoles()}
        console_name = console_names.get(
            installed_rom.console_id, f"Console #{installed_rom.console_id}"
        )
        games = library_service.list_games_for_matching(installed_rom.console_id)
        if not games:
            QMessageBox.information(
                self,
                "No games to match",
                f"No {console_name} games are synced locally yet — sync this console's "
                "catalog from Home's search first.",
            )
            return

        dialog = MatchRomDialog(installed_rom.file_path, console_name, games, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        game_id = dialog.selected_game_id()
        if game_id is None:
            return
        library_service.match_installed_rom_to_game(installed_rom.id, game_id)
        self.refresh()


def _describe_scan(result: RomFolderScanResult) -> str:
    """One line summarising the scan. The skipped counts are reported rather
    than hidden: a folder that comes back "0 new ROMs" is otherwise
    indistinguishable from one where every file was ambiguous.
    """
    parts = [f"{len(result.recorded)} new ROM(s) found"]
    if result.already_known_count:
        parts.append(f"{result.already_known_count} already known")
    if result.ambiguous_paths:
        parts.append(f"{len(result.ambiguous_paths)} ambiguous (console unclear)")
    if result.unrecognized_paths:
        parts.append(f"{len(result.unrecognized_paths)} not ROM files")
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
    return ", ".join(parts) + "."
