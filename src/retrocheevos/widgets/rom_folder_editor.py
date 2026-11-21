"""ROM folder editor shared by Library's Folders dialog and, from R24, Settings.

Folders are per console (`rom_folders.console_id`). The editor only edits the
folder list; scans run in the Library page, which owns the job slot and the
progress display, so the editor asks for them through signals.
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout,
    QWidget,
)

from retrocheevos.gui.components import button, text_label
from retrocheevos.gui.selection import selected_item
from retrocheevos.services import console_service, library_service
from retrocheevos.widgets.console_selector import ConsoleSelector

ROM_FOLDER_ID_ROLE = Qt.ItemDataRole.UserRole
EMPTY_HINT = "No ROM folders yet. Pick a console, then add the folder where its ROMs are."


class RomFolderEditor(QWidget):
    scan_requested = Signal(int)  # rom folder id
    scan_file_requested = Signal(int, str)  # console id, file path
    folders_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.console_selector = ConsoleSelector()
        self.console_selector.setAccessibleName("Console for the new folder")
        add_button = button("Add folder…", "primary")
        add_button.clicked.connect(self._on_add)
        top = QHBoxLayout()
        top.addWidget(text_label("Console"))
        top.addWidget(self.console_selector, stretch=1)
        top.addWidget(add_button)

        self.folder_list = QListWidget()
        self.folder_list.setAccessibleName("ROM folders")
        self._hint = text_label(EMPTY_HINT, "secondary", wrap=True)

        self._remove_button = button("Remove folder")
        self._remove_button.setToolTip("Stop indexing this folder (files are not touched)")
        self._remove_button.clicked.connect(self._on_remove)
        self._scan_button = button("Scan this folder")
        self._scan_button.clicked.connect(self._on_scan)
        scan_file = button("Scan a ROM file…")
        scan_file.setToolTip("Index one file for the console selected above")
        scan_file.clicked.connect(self._on_scan_file)
        actions = QHBoxLayout()
        actions.addWidget(self._remove_button)
        actions.addWidget(self._scan_button)
        actions.addStretch(1)
        actions.addWidget(scan_file)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self._hint)
        layout.addWidget(self.folder_list, stretch=1)
        layout.addLayout(actions)
        self.folder_list.currentRowChanged.connect(self._update_buttons)
        self.reload()

    def reload(self) -> None:
        consoles = console_service.list_configurable_consoles()
        names = {console.id: console.name for console in consoles}
        previous = self.console_selector.currentData()
        self.console_selector.clear()
        for console in consoles:
            self.console_selector.addItem(console.name, console.id)
        if previous is not None and (index := self.console_selector.findData(previous)) >= 0:
            self.console_selector.setCurrentIndex(index)

        self.folder_list.clear()
        for folder in library_service.list_rom_folders():
            label = names.get(folder.console_id, f"Console #{folder.console_id}") \
                if folder.console_id is not None else "Any console"
            item = QListWidgetItem(f"{label}: {folder.path}")
            item.setData(ROM_FOLDER_ID_ROLE, folder.id)
            self.folder_list.addItem(item)
        self._hint.setVisible(self.folder_list.count() == 0)
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_selection = selected_item(self.folder_list) is not None
        self._remove_button.setEnabled(has_selection)
        self._scan_button.setEnabled(has_selection)

    def _on_add(self) -> None:
        console_id = self.console_selector.currentData()
        if console_id is None:
            QMessageBox.warning(self, "No console selected", "Pick a console before adding its folder.")
            return
        path = QFileDialog.getExistingDirectory(self, "Select ROM Folder")
        if not path:
            return
        library_service.add_rom_folder(path, console_id=console_id)
        self.reload()
        self.folders_changed.emit()

    def _on_remove(self) -> None:
        item = selected_item(self.folder_list)
        if item is None:
            return
        library_service.remove_rom_folder(item.data(ROM_FOLDER_ID_ROLE))
        self.reload()
        self.folders_changed.emit()

    def _on_scan(self) -> None:
        item = selected_item(self.folder_list)
        if item is not None:
            self.scan_requested.emit(item.data(ROM_FOLDER_ID_ROLE))

    def _on_scan_file(self) -> None:
        console_id = self.console_selector.currentData()
        if console_id is None:
            QMessageBox.warning(self, "No console selected", "Pick the file's console above first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select ROM File")
        if path:
            self.scan_file_requested.emit(console_id, path)
