"""Library page (UI.md 3.3) — manual single-file scan, and Watch Folder
scanning (walks a configured ROM folder, auto-detects each file's console,
and organizes it — Settings > ROM folders manages the folder list itself).
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.dialogs.watch_folder_scan_dialog import WatchFolderScanDialog
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.library import WatchFolderScanPreview
from retrocheevos.services import console_service, library_service


class LibraryPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._play_worker: Optional[ServiceWorker] = None
        self._preview_worker: Optional[ServiceWorker] = None
        self._apply_worker: Optional[ServiceWorker] = None

        self._console_selector = QComboBox()
        self._console_selector.currentIndexChanged.connect(self._on_console_changed)

        self._installed_list = QListWidget()
        scan_button = QPushButton("Scan ROM File...")
        scan_button.clicked.connect(self._on_scan_file)
        play_button = QPushButton("Play Selected")
        play_button.clicked.connect(self._on_play_selected)

        self._watch_folder_selector = QComboBox()
        self._scan_watch_folder_button = QPushButton("Scan Watch Folder...")
        self._scan_watch_folder_button.clicked.connect(self._on_scan_watch_folder)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Console"))
        layout.addWidget(self._console_selector)
        layout.addWidget(QLabel("Installed ROMs"))
        layout.addWidget(self._installed_list)
        layout.addWidget(scan_button)
        layout.addWidget(play_button)
        layout.addWidget(QLabel("Watch Folder (add/remove folders in Settings)"))
        layout.addWidget(self._watch_folder_selector)
        layout.addWidget(self._scan_watch_folder_button)

    def refresh(self) -> None:
        current_console_id = self._console_selector.currentData()

        self._console_selector.blockSignals(True)
        self._console_selector.clear()
        self._console_selector.addItem("All consoles", None)
        for console in console_service.list_consoles():
            self._console_selector.addItem(console.name, console.id)
        # "All consoles" (data=None) is also `findData`'s result for an
        # unset current_console_id, so this still lands on index 0 first run.
        index = self._console_selector.findData(current_console_id)
        if index != -1:
            self._console_selector.setCurrentIndex(index)
        self._console_selector.blockSignals(False)

        self._refresh_installed_list()

        current_folder_id = self._watch_folder_selector.currentData()
        self._watch_folder_selector.clear()
        for folder in library_service.list_rom_folders():
            self._watch_folder_selector.addItem(folder.path, folder.id)
        if current_folder_id is not None:
            index = self._watch_folder_selector.findData(current_folder_id)
            if index != -1:
                self._watch_folder_selector.setCurrentIndex(index)

    def _refresh_installed_list(self) -> None:
        console_id = self._console_selector.currentData()

        self._installed_list.clear()
        for rom in library_service.list_installed_roms(console_id):
            status = f"game #{rom.game_id}" if rom.game_id else "unmatched"
            item = QListWidgetItem(f"{rom.file_path} ({status})")
            item.setData(Qt.ItemDataRole.UserRole, rom.game_id)
            self._installed_list.addItem(item)

    def _on_console_changed(self) -> None:
        self._refresh_installed_list()

    def _on_scan_file(self) -> None:
        console_id = self._console_selector.currentData()
        if console_id is None:
            QMessageBox.warning(
                self,
                "No console selected",
                "Pick a specific console above (not \"All consoles\") before scanning a ROM. "
                "If none are listed, sync consoles first (Settings/Sync).",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Select ROM File")
        if not file_path:
            return

        library_service.scan_and_record_rom(file_path, console_id)
        self.refresh()

    def _on_play_selected(self) -> None:
        item = self._installed_list.currentItem()
        if item is None:
            return
        game_id = item.data(Qt.ItemDataRole.UserRole)
        if game_id is None:
            QMessageBox.warning(self, "Not matched", "This ROM isn't matched to a game yet.")
            return

        self._play_worker = ServiceWorker(library_service.launch_game, game_id)
        self._play_worker.failed.connect(self._on_play_failed)
        self._play_worker.start()

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)

    def _on_scan_watch_folder(self) -> None:
        if self._watch_folder_selector.count() == 0:
            QMessageBox.warning(
                self, "No ROM folders", "Add a ROM folder in Settings before scanning."
            )
            return

        rom_folder_id = self._watch_folder_selector.currentData()
        self._scan_watch_folder_button.setEnabled(False)
        self._preview_worker = ServiceWorker(library_service.preview_watch_folder_scan, rom_folder_id)
        self._preview_worker.finished_ok.connect(
            lambda preview: self._on_watch_folder_preview_ready(rom_folder_id, preview)
        )
        self._preview_worker.failed.connect(self._on_watch_folder_scan_failed)
        self._preview_worker.start()

    def _on_watch_folder_preview_ready(
        self, rom_folder_id: int, preview: WatchFolderScanPreview
    ) -> None:
        self._scan_watch_folder_button.setEnabled(True)

        if not preview.confident and not preview.ambiguous:
            QMessageBox.information(
                self, "Watch Folder scan", "No new ROM files found in this folder."
            )
            return

        dialog = WatchFolderScanDialog(
            preview,
            console_service.list_consoles(),
            library_service.list_rom_destinations(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        decisions = dialog.decisions()
        if not decisions:
            return

        self._scan_watch_folder_button.setEnabled(False)
        self._apply_worker = ServiceWorker(
            library_service.apply_watch_folder_scan, rom_folder_id, decisions
        )
        self._apply_worker.finished_ok.connect(self._on_watch_folder_apply_done)
        self._apply_worker.failed.connect(self._on_watch_folder_scan_failed)
        self._apply_worker.start()

    def _on_watch_folder_apply_done(self, _result: object) -> None:
        self._scan_watch_folder_button.setEnabled(True)
        self.refresh()

    def _on_watch_folder_scan_failed(self, message: str) -> None:
        self._scan_watch_folder_button.setEnabled(True)
        QMessageBox.warning(self, "Watch Folder scan failed", message)
