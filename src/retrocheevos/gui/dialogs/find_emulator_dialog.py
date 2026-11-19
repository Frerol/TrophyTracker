"""Background search and explicit selection of a local emulator executable."""

from threading import Event
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.emulator_discovery import EmulatorCandidate, EmulatorSearchResult
from retrocheevos.services import emulator_discovery_service

DIALOG_WIDTH = 760
DIALOG_HEIGHT = 420


class FindEmulatorDialog(QDialog):
    def __init__(self, console_id: int, console_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f'Find Emulator — {console_name}')
        self.resize(DIALOG_WIDTH, DIALOG_HEIGHT)
        self._console_id = console_id
        self._worker: Optional[ServiceWorker] = None
        self._stop = Event()
        self._close_requested = False
        self.selected_candidate: Optional[EmulatorCandidate] = None

        layout = QVBoxLayout(self)
        instructions = QLabel(
            'Search for known emulators for this console. Choose a result, then save it in Settings.\n'
            'Portable installations can also be found by searching their folder.'
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self._common_button = QPushButton('Search common locations')
        self._common_button.clicked.connect(lambda: self._start_search())
        self._folder_button = QPushButton('Search folder...')
        self._folder_button.clicked.connect(self._search_folder)
        actions = QHBoxLayout()
        actions.addWidget(self._common_button)
        actions.addWidget(self._folder_button)
        actions.addStretch()
        layout.addLayout(actions)
        self._results = QListWidget()
        self._results.currentItemChanged.connect(self._update_selection)
        self._results.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self._results)
        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._use_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._use_button.setText('Use executable')
        self._use_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QTimer.singleShot(0, self._start_search)

    def _start_search(self, folder: Optional[str] = None) -> None:
        if self._worker is not None or self._close_requested:
            return
        self._stop.clear()
        self._results.clear()
        self._status.setText('Searching...')
        self._common_button.setEnabled(False)
        self._folder_button.setEnabled(False)
        self._use_button.setEnabled(False)
        self._worker = ServiceWorker(
            emulator_discovery_service.find_emulators, self._console_id,
            folder=folder, stop_requested=self._stop.is_set, stream_results=True,
        )
        self._worker.partial_result.connect(self._add_result)
        self._worker.finished_ok.connect(self._search_done)
        self._worker.failed.connect(self._search_failed)
        self._worker.finished.connect(self._thread_finished)
        self._worker.start()

    def _search_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Search for emulators in folder')
        if folder:
            self._start_search(folder)

    def _add_result(self, candidate: EmulatorCandidate) -> None:
        note = ' (libretro core required)' if candidate.requires_core else ''
        item = QListWidgetItem(f'{candidate.name}{note}\n{candidate.executable_path}')
        item.setData(Qt.ItemDataRole.UserRole, candidate)
        item.setToolTip(candidate.executable_path)
        self._results.addItem(item)
        if self._results.count() == 1:
            self._results.setCurrentRow(0)

    def _search_done(self, result: EmulatorSearchResult) -> None:
        text = f'{len(result.candidates)} executable(s) found.'
        if result.limited:
            text += ' Search limit reached; choose a folder to narrow the search.'
        elif not result.candidates:
            text += ' Try Search folder or use Browse in Settings.'
        self._status.setText(text)

    def _search_failed(self, message: str) -> None:
        self._status.setText(f'Search failed: {message}')

    def _thread_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._common_button.setEnabled(True)
        self._folder_button.setEnabled(True)
        self._update_selection()
        if self._close_requested:
            super().reject()

    def _update_selection(self) -> None:
        self._use_button.setEnabled(self._worker is None and self._results.currentItem() is not None)

    def accept(self) -> None:
        if self._worker is not None or self._results.currentItem() is None:
            return
        self.selected_candidate = self._results.currentItem().data(Qt.ItemDataRole.UserRole)
        super().accept()

    def reject(self) -> None:
        self._close_requested = True
        if self._worker is not None:
            self._stop.set()
            self._status.setText('Stopping search...')
            return
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if self._worker is not None:
            event.ignore()
            self.reject()
            return
        super().closeEvent(event)
