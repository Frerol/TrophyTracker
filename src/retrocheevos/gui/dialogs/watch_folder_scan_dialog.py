"""Watch Folder scan review dialog (UI.md 3.3) — shows what a scan would do
before any files move, and lets the user assign a console to files RA's own
hasher can't disambiguate on its own (`console_detection.DetectionResult`
candidates surfaced as `WatchFolderAmbiguity`).

Every file also needs a destination folder configured for its console
(Settings > ROM Destinations, `rom_destinations` table) before it can
actually be organized — files without one are shown but excluded from
`decisions()`, with an inline warning instead of silently vanishing.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.models.console import Console
from retrocheevos.models.library import WatchFolderMatch, WatchFolderScanPreview
from retrocheevos.models.rom_destination import RomDestination

_NO_DESTINATION_HINT = "no destination configured — set one in Settings > ROM Destinations"


def _describe_source(file_path: str, inner_member: Optional[str]) -> str:
    if inner_member:
        return f"{file_path} (extract {inner_member})"
    return file_path


class WatchFolderScanDialog(QDialog):
    """Confident matches with a configured destination are pre-checked and
    can be unchecked; those without one are shown disabled. Each ambiguous
    file gets its own console dropdown (defaulting to "Skip this file"),
    with a warning label that appears if the picked console has no
    destination configured. Nothing is moved until the user confirms via
    `decisions()`.
    """

    def __init__(
        self,
        preview: WatchFolderScanPreview,
        consoles: list[Console],
        destinations: list[RomDestination],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Watch Folder Scan")
        self.resize(560, 480)

        console_names = {console.id: console.name for console in consoles}
        self._configured_console_ids = {destination.console_id for destination in destinations}
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Detected matches ({len(preview.confident)}):"))
        self._confident_list = QListWidget()
        for match in preview.confident:
            console_name = console_names.get(match.console_id, f"Console {match.console_id}")
            label = _describe_source(match.file_path, match.inner_member)
            item = QListWidgetItem()
            if match.console_id in self._configured_console_ids:
                item.setText(f"{label}  ->  {console_name}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setText(f"{label}  ->  {console_name}  ({_NO_DESTINATION_HINT})")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            item.setData(Qt.ItemDataRole.UserRole, match)
            self._confident_list.addItem(item)
        layout.addWidget(self._confident_list)

        self._ambiguous_selectors: dict[str, QComboBox] = {}
        self._ambiguous_inner_members: dict[str, Optional[str]] = {}
        if preview.ambiguous:
            layout.addWidget(QLabel(f"Needs your input ({len(preview.ambiguous)}):"))
            for entry in preview.ambiguous:
                layout.addWidget(QLabel(_describe_source(entry.file_path, entry.inner_member)))
                self._ambiguous_inner_members[entry.file_path] = entry.inner_member

                selector = QComboBox()
                selector.addItem("Skip this file", None)
                for console_id in entry.candidate_console_ids:
                    console_name = console_names.get(console_id, f"Console {console_id}")
                    selector.addItem(console_name, console_id)

                warning_label = QLabel()
                warning_label.setVisible(False)
                selector.currentIndexChanged.connect(
                    lambda _index, box=selector, label=warning_label: self._update_ambiguous_warning(
                        box, label
                    )
                )

                layout.addWidget(selector)
                layout.addWidget(warning_label)
                self._ambiguous_selectors[entry.file_path] = selector

        if preview.unrecognized_paths:
            layout.addWidget(
                QLabel(f"Unrecognized extension, skipped ({len(preview.unrecognized_paths)}):")
            )
            unrecognized_list = QListWidget()
            for path in preview.unrecognized_paths:
                unrecognized_list.addItem(path)
            layout.addWidget(unrecognized_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Organize")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_ambiguous_warning(self, selector: QComboBox, warning_label: QLabel) -> None:
        console_id = selector.currentData()
        needs_destination = console_id is not None and console_id not in self._configured_console_ids
        warning_label.setText(f"⚠ {_NO_DESTINATION_HINT}" if needs_destination else "")
        warning_label.setVisible(needs_destination)

    def decisions(self) -> list[WatchFolderMatch]:
        """Checked confident matches plus every ambiguous file the user
        assigned a *configured* console to. Unchecked/skipped files, and any
        console without a destination folder, are left out — the caller
        should leave those exactly where they are.
        """
        decisions: list[WatchFolderMatch] = []

        for index in range(self._confident_list.count()):
            item = self._confident_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                decisions.append(item.data(Qt.ItemDataRole.UserRole))

        for file_path, selector in self._ambiguous_selectors.items():
            console_id = selector.currentData()
            if console_id is not None and console_id in self._configured_console_ids:
                decisions.append(
                    WatchFolderMatch(
                        file_path=file_path,
                        console_id=console_id,
                        inner_member=self._ambiguous_inner_members.get(file_path),
                    )
                )

        return decisions
