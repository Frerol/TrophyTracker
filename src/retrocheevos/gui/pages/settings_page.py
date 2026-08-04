"""Settings page (UI.md 3.7) — MVP scope: Accounts, ROM folders, Emulators,
ROM Destinations (Watch Folder organizing target per console).

Theme/Language/Cache management are deferred to the deepening pass.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.library.quick_link_suggestions import QUICK_LINK_SUGGESTIONS
from retrocheevos.services import console_service, library_service, lists_service, session_service
from retrocheevos.utils.enums import ListType


class SettingsPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)

        self._username_input = QLineEdit()
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        add_account_button = QPushButton("Add Account")
        add_account_button.clicked.connect(self._on_add_account)

        account_form = QFormLayout()
        account_form.addRow("Username", self._username_input)
        account_form.addRow("API Key", self._api_key_input)

        self._accounts_list = QListWidget()
        switch_button = QPushButton("Switch to Selected")
        switch_button.clicked.connect(self._on_switch_account)
        remove_account_button = QPushButton("Remove Selected")
        remove_account_button.clicked.connect(self._on_remove_account)
        account_buttons = QHBoxLayout()
        account_buttons.addWidget(switch_button)
        account_buttons.addWidget(remove_account_button)

        self._rom_folders_list = QListWidget()
        rom_folders_delegate = RemovableListDelegate(self._rom_folders_list)
        rom_folders_delegate.remove_requested.connect(self._remove_rom_folder)
        self._rom_folders_list.setItemDelegate(rom_folders_delegate)
        add_folder_button = QPushButton("Add ROM Folder...")
        add_folder_button.clicked.connect(self._on_add_rom_folder)
        remove_folder_button = QPushButton("Remove Selected Folder")
        remove_folder_button.clicked.connect(self._on_remove_rom_folder)
        folder_buttons = QHBoxLayout()
        folder_buttons.addWidget(add_folder_button)
        folder_buttons.addWidget(remove_folder_button)

        self._emulator_console_selector = QComboBox()
        self._emulator_path_input = QLineEdit()
        self._emulator_path_input.setPlaceholderText("Path to emulator executable")
        browse_emulator_button = QPushButton("Browse...")
        browse_emulator_button.clicked.connect(self._on_browse_emulator)
        emulator_path_row = QHBoxLayout()
        emulator_path_row.addWidget(self._emulator_path_input)
        emulator_path_row.addWidget(browse_emulator_button)

        self._emulator_args_input = QLineEdit()
        self._emulator_args_input.setPlaceholderText(
            "Optional arguments, e.g. -L cores/snes9x_libretro.dll {rom_path}"
        )

        save_emulator_button = QPushButton("Save Emulator")
        save_emulator_button.clicked.connect(self._on_save_emulator)

        emulator_form = QFormLayout()
        emulator_form.addRow("Console", self._emulator_console_selector)
        emulator_form.addRow("Executable", emulator_path_row)
        emulator_form.addRow("Arguments", self._emulator_args_input)

        self._emulators_list = QListWidget()
        emulators_delegate = RemovableListDelegate(self._emulators_list)
        emulators_delegate.remove_requested.connect(self._remove_emulator)
        self._emulators_list.setItemDelegate(emulators_delegate)
        remove_emulator_button = QPushButton("Remove Selected")
        remove_emulator_button.clicked.connect(self._on_remove_emulator)

        self._destination_console_selector = QComboBox()
        self._destination_path_input = QLineEdit()
        self._destination_path_input.setPlaceholderText("Folder where this console's ROMs live")
        browse_destination_button = QPushButton("Browse...")
        browse_destination_button.clicked.connect(self._on_browse_destination)
        destination_path_row = QHBoxLayout()
        destination_path_row.addWidget(self._destination_path_input)
        destination_path_row.addWidget(browse_destination_button)

        save_destination_button = QPushButton("Save Destination")
        save_destination_button.clicked.connect(self._on_save_destination)

        destination_form = QFormLayout()
        destination_form.addRow("Console", self._destination_console_selector)
        destination_form.addRow("Folder", destination_path_row)

        self._destinations_list = QListWidget()
        destinations_delegate = RemovableListDelegate(self._destinations_list)
        destinations_delegate.remove_requested.connect(self._remove_destination)
        self._destinations_list.setItemDelegate(destinations_delegate)
        remove_destination_button = QPushButton("Remove Selected")
        remove_destination_button.clicked.connect(self._on_remove_destination)

        self._quick_link_console_selector = QComboBox()
        self._quick_link_console_selector.currentIndexChanged.connect(
            self._on_quick_link_console_changed
        )
        self._quick_link_url_input = QLineEdit()
        self._quick_link_url_input.setPlaceholderText(
            "Reference URL for this console (e.g. a homebrew catalog or wiki)"
        )
        save_quick_link_button = QPushButton("Save Quick Link")
        save_quick_link_button.clicked.connect(self._on_save_quick_link)

        quick_link_form = QFormLayout()
        quick_link_form.addRow("Console", self._quick_link_console_selector)
        quick_link_form.addRow("URL", self._quick_link_url_input)

        self._quick_links_list = QListWidget()
        quick_links_delegate = RemovableListDelegate(self._quick_links_list)
        quick_links_delegate.remove_requested.connect(self._remove_quick_link)
        self._quick_links_list.setItemDelegate(quick_links_delegate)
        remove_quick_link_button = QPushButton("Remove Selected")
        remove_quick_link_button.clicked.connect(self._on_remove_quick_link)

        self._blocked_games_list = QListWidget()
        blocked_games_delegate = RemovableListDelegate(self._blocked_games_list)
        blocked_games_delegate.remove_requested.connect(self._unblock_game)
        self._blocked_games_list.setItemDelegate(blocked_games_delegate)
        unblock_button = QPushButton("Unblock Selected")
        unblock_button.clicked.connect(self._on_unblock_game)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel("Accounts"))
        layout.addLayout(account_form)
        layout.addWidget(add_account_button)
        layout.addWidget(self._accounts_list)
        layout.addLayout(account_buttons)
        layout.addWidget(QLabel("ROM Folders"))
        layout.addWidget(self._rom_folders_list)
        layout.addLayout(folder_buttons)
        layout.addWidget(QLabel("Emulators"))
        layout.addLayout(emulator_form)
        layout.addWidget(save_emulator_button)
        layout.addWidget(self._emulators_list)
        layout.addWidget(remove_emulator_button)
        layout.addWidget(QLabel("ROM Destinations (Watch Folder organizing target per console)"))
        layout.addLayout(destination_form)
        layout.addWidget(save_destination_button)
        layout.addWidget(self._destinations_list)
        layout.addWidget(remove_destination_button)
        layout.addWidget(QLabel("Quick Links (reference URL per console, opened from Library)"))
        layout.addLayout(quick_link_form)
        layout.addWidget(save_quick_link_button)
        layout.addWidget(self._quick_links_list)
        layout.addWidget(remove_quick_link_button)
        layout.addWidget(QLabel("Blocked Games"))
        layout.addWidget(self._blocked_games_list)
        layout.addWidget(unblock_button)
        layout.addStretch(1)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)

    def refresh(self) -> None:
        self._accounts_list.clear()
        for account in session_service.list_accounts():
            label = f"{account.username} (active)" if account.is_active else account.username
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, account.id)
            self._accounts_list.addItem(item)

        self._rom_folders_list.clear()
        for folder in library_service.list_rom_folders():
            item = QListWidgetItem(folder.path)
            item.setData(Qt.ItemDataRole.UserRole, folder.id)
            self._rom_folders_list.addItem(item)

        consoles = console_service.list_consoles()
        console_names = {console.id: console.name for console in consoles}
        previous_console = self._emulator_console_selector.currentData()
        self._emulator_console_selector.blockSignals(True)
        self._emulator_console_selector.clear()
        for console in consoles:
            self._emulator_console_selector.addItem(console.name, console.id)
        if previous_console is not None:
            index = self._emulator_console_selector.findData(previous_console)
            if index >= 0:
                self._emulator_console_selector.setCurrentIndex(index)
        self._emulator_console_selector.blockSignals(False)

        self._emulators_list.clear()
        for config in library_service.list_emulator_configs():
            console_name = console_names.get(config.console_id, f"Console #{config.console_id}")
            item = QListWidgetItem(f"{console_name}: {config.executable_path}")
            item.setData(Qt.ItemDataRole.UserRole, config.console_id)
            self._emulators_list.addItem(item)

        previous_destination_console = self._destination_console_selector.currentData()
        self._destination_console_selector.blockSignals(True)
        self._destination_console_selector.clear()
        for console in consoles:
            self._destination_console_selector.addItem(console.name, console.id)
        if previous_destination_console is not None:
            index = self._destination_console_selector.findData(previous_destination_console)
            if index >= 0:
                self._destination_console_selector.setCurrentIndex(index)
        self._destination_console_selector.blockSignals(False)

        self._destinations_list.clear()
        for destination in library_service.list_rom_destinations():
            console_name = console_names.get(
                destination.console_id, f"Console #{destination.console_id}"
            )
            item = QListWidgetItem(f"{console_name}: {destination.path}")
            item.setData(Qt.ItemDataRole.UserRole, destination.console_id)
            self._destinations_list.addItem(item)

        previous_quick_link_console = self._quick_link_console_selector.currentData()
        self._quick_link_console_selector.blockSignals(True)
        self._quick_link_console_selector.clear()
        for console in consoles:
            self._quick_link_console_selector.addItem(console.name, console.id)
        if previous_quick_link_console is not None:
            index = self._quick_link_console_selector.findData(previous_quick_link_console)
            if index >= 0:
                self._quick_link_console_selector.setCurrentIndex(index)
        self._quick_link_console_selector.blockSignals(False)

        self._quick_links_list.clear()
        for quick_link in library_service.list_quick_links():
            console_name = console_names.get(
                quick_link.console_id, f"Console #{quick_link.console_id}"
            )
            item = QListWidgetItem(f"{console_name}: {quick_link.url}")
            item.setData(Qt.ItemDataRole.UserRole, quick_link.console_id)
            self._quick_links_list.addItem(item)

        self._blocked_games_list.clear()
        account = self.app_context.active_account
        if account is not None:
            for game in lists_service.get_games_in_list(account.id, ListType.BLOCKED):
                console_name = console_names.get(game.console_id, f"Console #{game.console_id}")
                item = QListWidgetItem(f"{game.title} ({console_name})")
                item.setData(Qt.ItemDataRole.UserRole, game.id)
                self._blocked_games_list.addItem(item)

    def _on_add_account(self) -> None:
        username = self._username_input.text().strip()
        api_key = self._api_key_input.text().strip()
        if not username or not api_key:
            QMessageBox.warning(self, "Missing info", "Username and API Key are both required.")
            return
        session_service.add_account(username, api_key)
        self._username_input.clear()
        self._api_key_input.clear()
        self.app_context.refresh_active_account()
        self.refresh()

    def _on_switch_account(self) -> None:
        item = self._accounts_list.currentItem()
        if item is None:
            return
        session_service.switch_account(item.data(Qt.ItemDataRole.UserRole))
        self.app_context.refresh_active_account()
        self.refresh()

    def _on_remove_account(self) -> None:
        item = self._accounts_list.currentItem()
        if item is None:
            return
        session_service.remove_account(item.data(Qt.ItemDataRole.UserRole))
        self.app_context.refresh_active_account()
        self.refresh()

    def _on_add_rom_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select ROM Folder")
        if folder:
            library_service.add_rom_folder(folder)
            self.refresh()

    def _on_remove_rom_folder(self) -> None:
        item = self._rom_folders_list.currentItem()
        if item is None:
            return
        self._remove_rom_folder(item.data(Qt.ItemDataRole.UserRole))

    def _remove_rom_folder(self, folder_id: int) -> None:
        library_service.remove_rom_folder(folder_id)
        self.refresh()

    def _on_browse_emulator(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Emulator Executable")
        if file_path:
            self._emulator_path_input.setText(file_path)

    def _on_save_emulator(self) -> None:
        console_id = self._emulator_console_selector.currentData()
        executable_path = self._emulator_path_input.text().strip()
        if console_id is None or not executable_path:
            QMessageBox.warning(
                self, "Missing info", "Pick a console and an emulator executable."
            )
            return
        arguments_template = self._emulator_args_input.text().strip() or None
        library_service.set_emulator_config(console_id, executable_path, arguments_template)
        self._emulator_path_input.clear()
        self._emulator_args_input.clear()
        self.refresh()

    def _on_remove_emulator(self) -> None:
        item = self._emulators_list.currentItem()
        if item is None:
            return
        self._remove_emulator(item.data(Qt.ItemDataRole.UserRole))

    def _remove_emulator(self, console_id: int) -> None:
        library_service.remove_emulator_config(console_id)
        self.refresh()

    def _on_browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select ROM Destination Folder")
        if folder:
            self._destination_path_input.setText(folder)

    def _on_save_destination(self) -> None:
        console_id = self._destination_console_selector.currentData()
        path = self._destination_path_input.text().strip()
        if console_id is None or not path:
            QMessageBox.warning(self, "Missing info", "Pick a console and a destination folder.")
            return
        library_service.set_rom_destination(console_id, path)
        self._destination_path_input.clear()
        self.refresh()

    def _on_remove_destination(self) -> None:
        item = self._destinations_list.currentItem()
        if item is None:
            return
        self._remove_destination(item.data(Qt.ItemDataRole.UserRole))

    def _remove_destination(self, console_id: int) -> None:
        library_service.remove_rom_destination(console_id)
        self.refresh()

    def _on_quick_link_console_changed(self) -> None:
        # Always recomputed for the newly selected console, never left
        # over from whichever console was selected before: the already
        # saved link if one exists, else the curated suggestion, else
        # empty. Anything the user hasn't saved yet for the previous
        # console is intentionally abandoned on selection change — the
        # field always reflects the current selection's own state.
        console_id = self._quick_link_console_selector.currentData()
        if console_id is None:
            self._quick_link_url_input.clear()
            return

        existing = library_service.get_quick_link(console_id)
        if existing is not None:
            self._quick_link_url_input.setText(existing.url)
            return

        console_name = self._quick_link_console_selector.currentText()
        self._quick_link_url_input.setText(QUICK_LINK_SUGGESTIONS.get(console_name, ""))

    def _on_save_quick_link(self) -> None:
        console_id = self._quick_link_console_selector.currentData()
        url = self._quick_link_url_input.text().strip()
        if console_id is None or not url:
            QMessageBox.warning(self, "Missing info", "Pick a console and a URL.")
            return
        library_service.set_quick_link(console_id, url)
        self._quick_link_url_input.clear()
        self.refresh()

    def _on_remove_quick_link(self) -> None:
        item = self._quick_links_list.currentItem()
        if item is None:
            return
        self._remove_quick_link(item.data(Qt.ItemDataRole.UserRole))

    def _remove_quick_link(self, console_id: int) -> None:
        library_service.remove_quick_link(console_id)
        self.refresh()

    def _on_unblock_game(self) -> None:
        item = self._blocked_games_list.currentItem()
        if item is None:
            return
        self._unblock_game(item.data(Qt.ItemDataRole.UserRole))

    def _unblock_game(self, game_id: int) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        lists_service.remove_from_list(account.id, game_id, ListType.BLOCKED)
        self.refresh()
