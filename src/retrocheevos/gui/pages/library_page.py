"""Library page (UI.md 3.3) — MVP: manual scan only, no Watch Folder daemon yet."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.services import console_service, library_service


class LibraryPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._play_worker: Optional[ServiceWorker] = None

        self._console_selector = QComboBox()

        self._installed_list = QListWidget()
        scan_button = QPushButton("Scan ROM File...")
        scan_button.clicked.connect(self._on_scan_file)
        play_button = QPushButton("Play Selected")
        play_button.clicked.connect(self._on_play_selected)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Console"))
        layout.addWidget(self._console_selector)
        layout.addWidget(QLabel("Installed ROMs"))
        layout.addWidget(self._installed_list)
        layout.addWidget(scan_button)
        layout.addWidget(play_button)

    def refresh(self) -> None:
        self._console_selector.clear()
        for console in console_service.list_consoles():
            self._console_selector.addItem(console.name, console.id)

        self._installed_list.clear()
        for rom in library_service.list_installed_roms():
            status = f"game #{rom.game_id}" if rom.game_id else "unmatched"
            item = QListWidgetItem(f"{rom.file_path} ({status})")
            item.setData(Qt.ItemDataRole.UserRole, rom.game_id)
            self._installed_list.addItem(item)

    def _on_scan_file(self) -> None:
        if self._console_selector.count() == 0:
            QMessageBox.warning(
                self, "No consoles", "Sync consoles (Settings/Sync) before scanning a ROM."
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Select ROM File")
        if not file_path:
            return

        console_id = self._console_selector.currentData()
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
