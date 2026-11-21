"""Library's "Folders…" dialog: the shared `RomFolderEditor` in a window.

Asking for a scan closes the dialog so the Library page can show progress.
"""

from typing import Optional

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from retrocheevos.gui.components import text_label
from retrocheevos.widgets.rom_folder_editor import RomFolderEditor

NOTE = "Scanning indexes existing files. It does not move or download ROMs."


class FoldersDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ROM folders")
        self.resize(640, 420)
        self.scan_folder_id: Optional[int] = None
        self.scan_file: Optional[tuple[int, str]] = None
        self.editor = RomFolderEditor()
        self.editor.scan_requested.connect(self._on_scan)
        self.editor.scan_file_requested.connect(self._on_scan_file)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor, stretch=1)
        layout.addWidget(text_label(NOTE, "secondary", wrap=True))
        layout.addWidget(buttons)

    def _on_scan(self, folder_id: int) -> None:
        self.scan_folder_id = folder_id
        self.accept()

    def _on_scan_file(self, console_id: int, path: str) -> None:
        self.scan_file = (console_id, path)
        self.accept()
