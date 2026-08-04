"""Explorer filter bar (UI.md 3.2.1) — presentation-only (Architecture.md
§3.1), like `GameCard`. Never calls `services/` or `database/` directly.

Pill-button + popup design, matching the RetroAchievements site (screenshot
reference) rather than the earlier always-visible side panel
(`explorer_filter_panel.py`, removed) — same public shape (`apply_to()`,
`reset()`, `filters_changed`) so callers barely change. Multi-select popups
(Console, Type, Lists) embed their checkboxes via `QWidgetAction` rather
than plain `QAction`s, so clicking one checkbox doesn't close the whole
popup — the reference lets you tick several boxes before dismissing it.

UI.md §3.2.1 lists "Achievements (has/none)" and "Search with/without/all
achievements" as separate bullets, but `ExplorerFilters` only has one field
for this (`has_achievements: Optional[bool]`) — treated as the same concept
described twice in the planning doc, per user confirmation (unchanged from
the previous panel).
"""

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from retrocheevos.core.explorer import ExplorerFilters
from retrocheevos.models.console import Console
from retrocheevos.utils.enums import GameType, ListType

_ALL_CONSOLES_LABEL = "All Consoles"

_ACHIEVEMENTS_OPTIONS = [
    ("All games", None),
    ("With achievements", True),
    ("Without achievements", False),
]

_GAME_TYPE_LABELS = {
    GameType.RETAIL: "Retail",
    GameType.HOMEBREW: "Homebrew",
    GameType.HACK: "Hack",
    GameType.DEMO: "Demo",
    GameType.PROTOTYPE: "Prototype",
}

# Want to Play/Playing/Following narrow results to those lists. Completed/
# Abandoned/Mastered are separate "hidden by default, reveal" toggles
# (Database.md 4.1, UI.md 3.2.1's default-hidden note) — both groups share
# one "Lists" pill so the bar doesn't need 3-4 extra pills for them.
_INCLUDE_LIST_LABELS = {
    ListType.WANT_TO_PLAY: "Want to Play",
    ListType.PLAYING: "Playing",
    ListType.FOLLOWING: "Following",
}


class ExplorerFilterBar(QWidget):
    filters_changed = Signal()

    def __init__(self) -> None:
        super().__init__()

        self._console_list = QListWidget()
        self._console_list.itemChanged.connect(self._on_console_item_changed)
        self._console_pill = self._make_popup_pill("Console", self._console_list)

        self._game_type_checkboxes: dict[GameType, QCheckBox] = {}
        type_container = QWidget()
        type_layout = QVBoxLayout(type_container)
        for game_type, label in _GAME_TYPE_LABELS.items():
            checkbox = QCheckBox(label)
            checkbox.stateChanged.connect(self._on_type_changed)
            self._game_type_checkboxes[game_type] = checkbox
            type_layout.addWidget(checkbox)
        self._type_pill = self._make_popup_pill("Type", type_container)

        self._achievements_pill = QPushButton("Achievements")
        self._achievements_pill.setProperty("baseLabel", "Achievements")
        self._achievements_value: Optional[bool] = None
        achievements_menu = QMenu(self._achievements_pill)
        achievements_group = QActionGroup(achievements_menu)
        achievements_group.setExclusive(True)
        for label, value in _ACHIEVEMENTS_OPTIONS:
            action = QAction(label, achievements_menu)
            action.setCheckable(True)
            action.setChecked(value is None)
            action.triggered.connect(self._make_achievements_handler(value, label))
            achievements_group.addAction(action)
            achievements_menu.addAction(action)
        self._achievements_pill.setMenu(achievements_menu)

        self._median_time_pill = QPushButton("Median Time")
        self._median_time_pill.setCheckable(True)
        self._median_time_pill.toggled.connect(self._on_median_time_toggled)

        self._installed_pill = QPushButton("Installed")
        self._installed_pill.setCheckable(True)
        self._installed_pill.toggled.connect(self._on_installed_toggled)

        self._include_list_checkboxes: dict[ListType, QCheckBox] = {}
        self._show_completed_checkbox = QCheckBox("Completed")
        self._show_abandoned_checkbox = QCheckBox("Abandoned")
        self._show_mastered_checkbox = QCheckBox("Mastered")
        lists_container = QWidget()
        lists_layout = QVBoxLayout(lists_container)
        for list_type, label in _INCLUDE_LIST_LABELS.items():
            checkbox = QCheckBox(label)
            checkbox.stateChanged.connect(self._on_lists_changed)
            self._include_list_checkboxes[list_type] = checkbox
            lists_layout.addWidget(checkbox)
        for checkbox in (
            self._show_completed_checkbox,
            self._show_abandoned_checkbox,
            self._show_mastered_checkbox,
        ):
            checkbox.stateChanged.connect(self._on_lists_changed)
            lists_layout.addWidget(checkbox)
        self._lists_pill = self._make_popup_pill("Lists", lists_container)

        reset_button = QPushButton("Reset ✕")
        reset_button.clicked.connect(self._on_reset_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in (
            self._console_pill,
            self._type_pill,
            self._achievements_pill,
            self._median_time_pill,
            self._installed_pill,
            self._lists_pill,
            reset_button,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)

        self._update_console_pill_label()
        self._update_type_pill_label()
        self._update_lists_pill_label()

    def _make_popup_pill(self, label: str, content: QWidget) -> QPushButton:
        """A pill whose click shows `content` in a popup. Embedding `content`
        via `QWidgetAction` (not adding plain `QAction`s) means clicks inside
        it don't auto-close the menu — needed so multi-checkbox popups let
        you tick several boxes before dismissing.
        """
        button = QPushButton(label)
        button.setProperty("baseLabel", label)
        menu = QMenu(button)
        widget_action = QWidgetAction(menu)
        widget_action.setDefaultWidget(content)
        menu.addAction(widget_action)
        button.setMenu(menu)
        return button

    # --- Console -----------------------------------------------------

    def set_available_consoles(self, consoles: list[Console]) -> None:
        """Repopulates the console checklist, preserving which ids were checked.

        Item 0 is always "All Consoles" (data=None) — checking it clears any
        specific console; checking a specific console unchecks it.
        """
        checked_ids = self._checked_console_ids()
        self._console_list.blockSignals(True)
        self._console_list.clear()

        all_item = QListWidgetItem(_ALL_CONSOLES_LABEL)
        all_item.setFlags(all_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        all_item.setCheckState(
            Qt.CheckState.Unchecked if checked_ids else Qt.CheckState.Checked
        )
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self._console_list.addItem(all_item)

        for console in consoles:
            item = QListWidgetItem(console.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if console.id in checked_ids else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, console.id)
            self._console_list.addItem(item)
        self._console_list.blockSignals(False)
        self._update_console_pill_label()

    def _checked_console_ids(self) -> set[int]:
        checked = set()
        for index in range(self._console_list.count()):
            item = self._console_list.item(index)
            console_id = item.data(Qt.ItemDataRole.UserRole)
            if console_id is not None and item.checkState() == Qt.CheckState.Checked:
                checked.add(console_id)
        return checked

    def _on_console_item_changed(self, changed_item: QListWidgetItem) -> None:
        is_all_item = changed_item.data(Qt.ItemDataRole.UserRole) is None
        checked = changed_item.checkState() == Qt.CheckState.Checked

        self._console_list.blockSignals(True)
        try:
            if is_all_item and checked:
                for index in range(1, self._console_list.count()):
                    self._console_list.item(index).setCheckState(Qt.CheckState.Unchecked)
            elif not is_all_item and checked:
                self._console_list.item(0).setCheckState(Qt.CheckState.Unchecked)
            elif not self._checked_console_ids():
                self._console_list.item(0).setCheckState(Qt.CheckState.Checked)
        finally:
            self._console_list.blockSignals(False)

        self._update_console_pill_label()
        self.filters_changed.emit()

    def _update_console_pill_label(self) -> None:
        checked_names = [
            self._console_list.item(i).text()
            for i in range(self._console_list.count())
            if self._console_list.item(i).data(Qt.ItemDataRole.UserRole) is not None
            and self._console_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        self._set_pill_text(self._console_pill, self._summarize(checked_names))

    # --- Type ----------------------------------------------------------

    def _on_type_changed(self, _state: int) -> None:
        self._update_type_pill_label()
        self.filters_changed.emit()

    def _update_type_pill_label(self) -> None:
        checked_labels = [
            _GAME_TYPE_LABELS[game_type]
            for game_type, checkbox in self._game_type_checkboxes.items()
            if checkbox.isChecked()
        ]
        self._set_pill_text(self._type_pill, self._summarize(checked_labels))

    # --- Achievements ----------------------------------------------------

    def _make_achievements_handler(self, value: Optional[bool], label: str):
        def _handler(checked: bool) -> None:
            if not checked:
                return
            self._achievements_value = value
            self._set_pill_text(self._achievements_pill, None if value is None else label)
            self.filters_changed.emit()

        return _handler

    # --- Median Time / Installed (plain toggle pills, no popup) --------

    def _on_median_time_toggled(self, checked: bool) -> None:
        self._median_time_pill.setText("Median Time: Known only" if checked else "Median Time")
        self.filters_changed.emit()

    def _on_installed_toggled(self, checked: bool) -> None:
        self._installed_pill.setText("Installed: Yes" if checked else "Installed")
        self.filters_changed.emit()

    # --- Lists -----------------------------------------------------------

    def _on_lists_changed(self, _state: int) -> None:
        self._update_lists_pill_label()
        self.filters_changed.emit()

    def _update_lists_pill_label(self) -> None:
        active = sum(
            checkbox.isChecked()
            for checkbox in (
                *self._include_list_checkboxes.values(),
                self._show_completed_checkbox,
                self._show_abandoned_checkbox,
                self._show_mastered_checkbox,
            )
        )
        self._set_pill_text(self._lists_pill, f"{active} active" if active else None)

    # --- Reset / shared helpers -------------------------------------------

    def _on_reset_clicked(self) -> None:
        self.reset()
        self.filters_changed.emit()

    def _set_pill_text(self, button: QPushButton, value_summary: Optional[str]) -> None:
        base_label = button.property("baseLabel")
        button.setText(f"{base_label}: {value_summary}" if value_summary else base_label)

    @staticmethod
    def _summarize(values: list[str]) -> Optional[str]:
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        return f"{len(values)} selected"

    def apply_to(self, base_filters: ExplorerFilters) -> ExplorerFilters:
        """Combines this bar's state with `base_filters` (the page owns `search_text`)."""
        console_ids = self._checked_console_ids()
        game_types = [
            game_type
            for game_type, checkbox in self._game_type_checkboxes.items()
            if checkbox.isChecked()
        ]
        list_types = [
            list_type
            for list_type, checkbox in self._include_list_checkboxes.items()
            if checkbox.isChecked()
        ]

        return replace(
            base_filters,
            console_ids=list(console_ids) or None,
            game_types=game_types or None,
            has_achievements=self._achievements_value,
            require_known_median_time=self._median_time_pill.isChecked(),
            installed_only=self._installed_pill.isChecked(),
            list_types_any_of=list_types or None,
            show_completed=self._show_completed_checkbox.isChecked(),
            show_abandoned=self._show_abandoned_checkbox.isChecked(),
            show_mastered=self._show_mastered_checkbox.isChecked(),
        )

    def reset(self) -> None:
        """Clears every control back to its default ("All Consoles" / "All games")."""
        self._console_list.blockSignals(True)
        for index in range(self._console_list.count()):
            item = self._console_list.item(index)
            is_all_item = item.data(Qt.ItemDataRole.UserRole) is None
            item.setCheckState(Qt.CheckState.Checked if is_all_item else Qt.CheckState.Unchecked)
        self._console_list.blockSignals(False)
        self._update_console_pill_label()

        for checkbox in self._game_type_checkboxes.values():
            checkbox.setChecked(False)
        self._update_type_pill_label()

        self._achievements_value = None
        self._set_pill_text(self._achievements_pill, None)
        for action in self._achievements_pill.menu().actions():
            action.setChecked(action.text() == _ACHIEVEMENTS_OPTIONS[0][0])

        self._median_time_pill.setChecked(False)
        self._installed_pill.setChecked(False)

        for checkbox in self._include_list_checkboxes.values():
            checkbox.setChecked(False)
        self._show_completed_checkbox.setChecked(False)
        self._show_abandoned_checkbox.setChecked(False)
        self._show_mastered_checkbox.setChecked(False)
        self._update_lists_pill_label()
