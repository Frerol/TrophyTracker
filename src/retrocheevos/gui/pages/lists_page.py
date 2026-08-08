"""Lists page (UI.md 3.6) — one list at a time, plus create/rename/delete.

Every list here renders the same way: `ListEntryRow` — cover, title, console
and a "−". These are places you go to *curate*, not to browse or launch, so
there is no Play button and no "..." menu.

Blocked is the only list the app ships (`core/lists.py::PREDEFINED_LISTS`);
everything else is one the user made. Blocked can't be renamed or deleted,
because Explorer resolves it by slug on every search to hide its games.

Library used to be an entry in this dropdown and no longer is — it became
its own page (`gui/pages/library_page.py`). It never behaved like a list:
no stored rows, no manual membership, and a cover-art grid nothing else
shared.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.models.list_definition import ListDefinition
from retrocheevos.services import console_service, lists_service
from retrocheevos.widgets.list_entry_row import ListEntryRow

EMPTY_LIST_TEXT = "Nothing in this list yet."
NO_LISTS_TEXT = 'No lists yet — "New List..." creates one.'


class ListsPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._image_loader = ImageLoader()
        self._definitions: list[ListDefinition] = []

        self._list_selector = QComboBox()
        self._list_selector.currentIndexChanged.connect(self.refresh)

        new_button = QPushButton("New List...")
        new_button.clicked.connect(self._on_create_list)
        self._rename_button = QPushButton("Rename...")
        self._rename_button.clicked.connect(self._on_rename_list)
        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self._on_delete_list)

        selector_row = QHBoxLayout()
        selector_row.addWidget(self._list_selector, stretch=1)
        selector_row.addWidget(new_button)
        selector_row.addWidget(self._rename_button)
        selector_row.addWidget(self._delete_button)

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch(1)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._rows_container)

        layout = QVBoxLayout(self)
        layout.addLayout(selector_row)
        layout.addWidget(scroll_area, stretch=1)

    def refresh(self) -> None:
        self._clear_rows()

        account = self.app_context.active_account
        if account is None:
            return

        self._reload_definitions(account.id)
        definition = self._current_definition()
        if definition is None:
            self._rows_layout.insertWidget(0, QLabel(NO_LISTS_TEXT))
            self._rename_button.setEnabled(False)
            self._delete_button.setEnabled(False)
            return

        # Blocked is the only special one left: renaming it would make
        # Explorer's "Block" action point at a differently-named list, and
        # deleting it would silently switch off the blocked filter.
        self._rename_button.setEnabled(not definition.is_blocked)
        self._delete_button.setEnabled(not definition.is_predefined)

        console_names = {console.id: console.name for console in console_service.list_consoles()}
        games = lists_service.get_games_in_list(account.id, definition.id)
        if not games:
            self._rows_layout.insertWidget(0, QLabel(EMPTY_LIST_TEXT))
            return

        tooltip = "Unblock this game" if definition.is_blocked else "Remove from this list"
        for index, game in enumerate(games):
            row = ListEntryRow(
                game,
                self._image_loader,
                console_name=console_names.get(game.console_id),
                remove_tooltip=tooltip,
            )
            row.remove_requested.connect(self._on_remove_from_list)
            # Before the trailing stretch, so rows stack from the top and
            # keep their natural height instead of being spread down the page.
            self._rows_layout.insertWidget(index, row)

    def _clear_rows(self) -> None:
        # Stops at 1, not 0: the trailing stretch is what keeps the rows
        # packed at the top, and removing it would let them spread again.
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _reload_definitions(self, account_id: int) -> None:
        """Repopulates the selector while holding on to the current
        selection — `refresh` is connected to `currentIndexChanged`, so the
        signal has to be blocked or rebuilding the list re-enters here."""
        previous_id = self._list_selector.currentData()
        self._definitions = lists_service.list_definitions(account_id)

        self._list_selector.blockSignals(True)
        self._list_selector.clear()
        for definition in self._definitions:
            self._list_selector.addItem(definition.name, definition.id)
        if previous_id is not None:
            index = self._list_selector.findData(previous_id)
            if index >= 0:
                self._list_selector.setCurrentIndex(index)
        self._list_selector.blockSignals(False)

    def _current_definition(self) -> Optional[ListDefinition]:
        list_id = self._list_selector.currentData()
        return next((d for d in self._definitions if d.id == list_id), None)

    # --- list management ---------------------------------------------

    def _on_create_list(self) -> None:
        account = self.app_context.active_account
        if account is None:
            # Said out loud rather than returning silently: a button that
            # does nothing at all is indistinguishable from one that failed,
            # which is exactly the ambiguity a "my list wasn't saved" report
            # leaves you in.
            QMessageBox.warning(
                self, "Not signed in", "Sign in before creating lists."
            )
            return
        name, accepted = QInputDialog.getText(self, "New List", "Name:")
        if not accepted or not name.strip():
            return
        try:
            created = lists_service.create_list(account.id, name)
        except ValueError as error:
            QMessageBox.warning(self, "Can't create list", str(error))
            return
        self._reload_definitions(account.id)
        index = self._list_selector.findData(created.id)
        if index >= 0:
            self._list_selector.setCurrentIndex(index)
        self.refresh()

    def _on_rename_list(self) -> None:
        account = self.app_context.active_account
        definition = self._current_definition()
        if account is None or definition is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename List", "Name:", text=definition.name
        )
        if not accepted:
            return
        try:
            lists_service.rename_list(account.id, definition.id, name)
        except ValueError as error:
            QMessageBox.warning(self, "Can't rename list", str(error))
            return
        self.refresh()

    def _on_delete_list(self) -> None:
        account = self.app_context.active_account
        definition = self._current_definition()
        if account is None or definition is None:
            return
        confirmed = QMessageBox.question(
            self,
            "Delete list",
            f'Delete "{definition.name}"? The games themselves aren\'t touched.',
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            lists_service.delete_list(definition.id)
        except ValueError as error:
            QMessageBox.warning(self, "Can't delete list", str(error))
            return
        self._list_selector.setCurrentIndex(0)
        self.refresh()

    def _on_remove_from_list(self, game_id: int) -> None:
        account = self.app_context.active_account
        definition = self._current_definition()
        if account is None or definition is None:
            return
        lists_service.remove_from_list(account.id, game_id, definition.id)
        self.refresh()
