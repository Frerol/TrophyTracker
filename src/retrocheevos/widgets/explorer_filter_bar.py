"""Explorer filter bar (UI.md 3.2.1) — presentation-only (Architecture.md
§3.1), like every other widget here. Never calls `services/` or `database/` directly.

Pill-button + popup design, matching the RetroAchievements site (screenshot
reference) rather than the earlier always-visible side panel
(`explorer_filter_panel.py`, removed) — same public shape (`apply_to()`,
`reset()`, `filters_changed`) so callers barely change. Multi-select popups
(Console, Type, Lists) embed their checkboxes via `QWidgetAction` rather
than plain `QAction`s, so clicking one checkbox doesn't close the whole
popup — the reference lets you tick several boxes before dismissing it.

Games without an achievement set are never synced/stored at all
(`services/sync_service.py`, `database/repositories/game_repository.py`), so
there is no "Achievements (has/none)" filter here — every game already has
achievements, unconditionally.
"""

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from retrocheevos.core.explorer import ExplorerFilters
from retrocheevos.models.console import Console
from retrocheevos.utils.enums import GameType

_ALL_CONSOLES_LABEL = "All Consoles"
_ALL_TYPES_LABEL = "All"

MIN_MEDIAN_TIME_MINUTES = 1
# 10 hours — past this the filter stops being a "what fits in my evening"
# question, which is the only thing it's for.
MAX_MEDIAN_TIME_MINUTES = 600
DEFAULT_MEDIAN_TIME_MINUTES = 30

_GAME_TYPE_LABELS = {
    GameType.RETAIL: "Retail",
    GameType.HOMEBREW: "Homebrew",
    GameType.HACK: "Hack",
    GameType.DEMO: "Demo",
    GameType.PROTOTYPE: "Prototype",
}

# The "Lists" pill's checkboxes are built at runtime from the lists the
# account actually has (`set_list_options`), not from a fixed table here.
# They used to be a hardcoded Want to Play/Playing pair plus
# Completed/Abandoned reveal toggles; with user-created lists (Bloco 12)
# there's no fixed set to hardcode, and the four predefined lists those
# entries pointed at were deleted in migration v16.
#
# Mastered/Beaten still have no checkbox — `core/explorer.py::search_games`
# excludes them unconditionally, no reveal option (per user decision).
_NO_LISTS_TEXT = "No lists yet"


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
        # "All" mirrors the Console pill's "All Consoles" entry: with nothing
        # ticked the filter is already inactive, but there was no way to say
        # so — you had to remember to untick everything by hand.
        self._all_types_checkbox = QCheckBox(_ALL_TYPES_LABEL)
        self._all_types_checkbox.setChecked(True)
        self._all_types_checkbox.stateChanged.connect(self._on_all_types_changed)
        type_layout.addWidget(self._all_types_checkbox)
        for game_type, label in _GAME_TYPE_LABELS.items():
            checkbox = QCheckBox(label)
            checkbox.stateChanged.connect(self._on_type_changed)
            self._game_type_checkboxes[game_type] = checkbox
            type_layout.addWidget(checkbox)
        self._type_pill = self._make_popup_pill("Type", type_container)

        # A duration entry, not a yes/no toggle: "what can I finish tonight"
        # is the actual question, and an "any known median time" boolean
        # never answered it. Inactive until the user applies a value.
        self._max_median_time_minutes: Optional[int] = None
        median_time_container = QWidget()
        median_time_layout = QVBoxLayout(median_time_container)
        median_time_layout.addWidget(QLabel("Beat in at most (minutes):"))
        self._median_time_spinbox = QSpinBox()
        self._median_time_spinbox.setRange(
            MIN_MEDIAN_TIME_MINUTES, MAX_MEDIAN_TIME_MINUTES
        )
        self._median_time_spinbox.setValue(DEFAULT_MEDIAN_TIME_MINUTES)
        median_time_layout.addWidget(self._median_time_spinbox)
        median_time_buttons = QHBoxLayout()
        apply_median_time_button = QPushButton("Apply")
        apply_median_time_button.clicked.connect(self._on_median_time_applied)
        clear_median_time_button = QPushButton("Clear")
        clear_median_time_button.clicked.connect(self._on_median_time_cleared)
        median_time_buttons.addWidget(apply_median_time_button)
        median_time_buttons.addWidget(clear_median_time_button)
        median_time_layout.addLayout(median_time_buttons)
        self._median_time_pill = self._make_popup_pill("Median Time", median_time_container)

        self._installed_pill = QPushButton("Installed")
        self._installed_pill.setCheckable(True)
        self._installed_pill.toggled.connect(self._on_installed_toggled)

        self._include_list_checkboxes: dict[int, QCheckBox] = {}
        self._lists_container = QWidget()
        self._lists_layout = QVBoxLayout(self._lists_container)
        self._lists_layout.addWidget(QLabel(_NO_LISTS_TEXT))
        self._lists_pill = self._make_popup_pill("Lists", self._lists_container)

        reset_button = QPushButton("Reset ✕")
        reset_button.clicked.connect(self._on_reset_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in (
            self._console_pill,
            self._type_pill,
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
        # Ticking a specific type implicitly means "not all of them", and
        # unticking the last one lands back on All — same mutual exclusion
        # the Console pill's "All Consoles" item has.
        self._all_types_checkbox.blockSignals(True)
        self._all_types_checkbox.setChecked(not self._any_type_checked())
        self._all_types_checkbox.blockSignals(False)
        self._update_type_pill_label()
        self.filters_changed.emit()

    def _on_all_types_changed(self, _state: int) -> None:
        if not self._all_types_checkbox.isChecked():
            # Unticking All directly is meaningless — with no specific type
            # picked the filter would be in the same state either way, so
            # snap it back rather than allow a no-op "nothing selected".
            if not self._any_type_checked():
                self._all_types_checkbox.blockSignals(True)
                self._all_types_checkbox.setChecked(True)
                self._all_types_checkbox.blockSignals(False)
            return

        for checkbox in self._game_type_checkboxes.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        self._update_type_pill_label()
        self.filters_changed.emit()

    def _any_type_checked(self) -> bool:
        return any(checkbox.isChecked() for checkbox in self._game_type_checkboxes.values())

    def _update_type_pill_label(self) -> None:
        checked_labels = [
            _GAME_TYPE_LABELS[game_type]
            for game_type, checkbox in self._game_type_checkboxes.items()
            if checkbox.isChecked()
        ]
        self._set_pill_text(self._type_pill, self._summarize(checked_labels))

    # --- Median Time (popup with a minutes entry) -----------------------

    def _on_median_time_applied(self) -> None:
        self._max_median_time_minutes = self._median_time_spinbox.value()
        self._update_median_time_pill_label()
        self.filters_changed.emit()

    def _on_median_time_cleared(self) -> None:
        self._max_median_time_minutes = None
        self._update_median_time_pill_label()
        self.filters_changed.emit()

    def _update_median_time_pill_label(self) -> None:
        self._set_pill_text(
            self._median_time_pill,
            None
            if self._max_median_time_minutes is None
            else f"≤{self._max_median_time_minutes}m",
        )

    # --- Installed (plain toggle pill, no popup) ------------------------

    def _on_installed_toggled(self, checked: bool) -> None:
        self._installed_pill.setText("Installed: Yes" if checked else "Installed")
        self.filters_changed.emit()

    # --- Lists -----------------------------------------------------------

    def _on_lists_changed(self, _state: int) -> None:
        self._update_lists_pill_label()
        self.filters_changed.emit()

    def set_list_options(self, list_options: list[tuple[int, str]]) -> None:
        """Rebuild the Lists pill from `(list_id, name)`.

        Ticked boxes are carried across by id so refreshing the page — which
        happens on every visit — doesn't silently clear an active filter. A
        list the user deleted simply doesn't come back.
        """
        previously_checked = {
            list_id
            for list_id, checkbox in self._include_list_checkboxes.items()
            if checkbox.isChecked()
        }
        self._include_list_checkboxes.clear()
        while self._lists_layout.count():
            item = self._lists_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not list_options:
            self._lists_layout.addWidget(QLabel(_NO_LISTS_TEXT))
            self._update_lists_pill_label()
            return

        for list_id, name in list_options:
            checkbox = QCheckBox(name)
            checkbox.setChecked(list_id in previously_checked)
            checkbox.stateChanged.connect(self._on_lists_changed)
            self._include_list_checkboxes[list_id] = checkbox
            self._lists_layout.addWidget(checkbox)
        self._update_lists_pill_label()

    def _update_lists_pill_label(self) -> None:
        active = sum(
            checkbox.isChecked() for checkbox in self._include_list_checkboxes.values()
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
        list_ids = [
            list_id
            for list_id, checkbox in self._include_list_checkboxes.items()
            if checkbox.isChecked()
        ]

        return replace(
            base_filters,
            console_ids=list(console_ids) or None,
            game_types=game_types or None,
            max_median_time_minutes=self._max_median_time_minutes,
            installed_only=self._installed_pill.isChecked(),
            list_ids_any_of=list_ids or None,
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
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        self._all_types_checkbox.blockSignals(True)
        self._all_types_checkbox.setChecked(True)
        self._all_types_checkbox.blockSignals(False)
        self._update_type_pill_label()

        self._max_median_time_minutes = None
        self._median_time_spinbox.setValue(DEFAULT_MEDIAN_TIME_MINUTES)
        self._update_median_time_pill_label()
        self._installed_pill.setChecked(False)

        for checkbox in self._include_list_checkboxes.values():
            checkbox.setChecked(False)
        self._update_lists_pill_label()
