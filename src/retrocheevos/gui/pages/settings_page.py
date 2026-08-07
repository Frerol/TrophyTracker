"""Settings page (UI.md 3.7) — MVP scope: Accounts, Emulators, Profile sync.

ROM Folders left too: folders are per-console now and live under the Lists
page's Library view, next to the grid they fill and the scan that reads
them. Adding a folder here meant leaving the page to do anything with it.

ROM Destinations and Quick Links were removed in Bloco 11: destinations only
existed to tell the Watch Folder organizer where to move files, and nothing
moves files any more; the Quick Link button they fed lived on the page that
became ROM Location.

Blocked Games left in Bloco 12. Blocked is a list like any other now, so it
lives on the Lists page with the rest of them and unblocking is the "−"
button on its cards — managing it from two places would have meant two
implementations of the same thing.

Theme/Language/Cache management are deferred to the deepening pass.
"""

from typing import Optional

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
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.services import (
    console_service,
    library_service,
    session_service,
    sync_service,
)


class SettingsPage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._sync_profile_worker: Optional[ServiceWorker] = None

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

        # RetroArch and other libretro frontends are one executable plus a
        # core `.dll` per system, so "the emulator for this console" needs
        # two paths. Optional: emulators with a real per-console binary
        # leave it empty and nothing changes for them.
        self._emulator_core_input = QLineEdit()
        self._emulator_core_input.setPlaceholderText(
            "Optional libretro core, e.g. cores/snes9x_libretro.dll (RetroArch)"
        )
        browse_core_button = QPushButton("Browse...")
        browse_core_button.clicked.connect(self._on_browse_core)
        emulator_core_row = QHBoxLayout()
        emulator_core_row.addWidget(self._emulator_core_input)
        emulator_core_row.addWidget(browse_core_button)

        emulator_form = QFormLayout()
        emulator_form.addRow("Console", self._emulator_console_selector)
        emulator_form.addRow("Executable", emulator_path_row)
        emulator_form.addRow("Core", emulator_core_row)
        emulator_form.addRow("Arguments", self._emulator_args_input)

        self._emulators_list = QListWidget()
        emulators_delegate = RemovableListDelegate(self._emulators_list)
        emulators_delegate.remove_requested.connect(self._remove_emulator)
        self._emulators_list.setItemDelegate(emulators_delegate)
        remove_emulator_button = QPushButton("Remove Selected")
        remove_emulator_button.clicked.connect(self._on_remove_emulator)

        # Absorbed from the retired Profile page. Home syncs the profile on
        # its own, but only opportunistically and at most every
        # `sync_service.PROFILE_SYNC_STALE_AFTER` — this is the explicit
        # override for "refresh my points/badges right now", and the only
        # place a sync failure is surfaced rather than just logged.
        self._sync_profile_button = QPushButton("Sync Profile")
        self._sync_profile_button.clicked.connect(self._on_sync_profile)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel("Accounts"))
        layout.addLayout(account_form)
        layout.addWidget(add_account_button)
        layout.addWidget(self._accounts_list)
        layout.addLayout(account_buttons)
        layout.addWidget(QLabel("Emulators"))
        layout.addLayout(emulator_form)
        layout.addWidget(save_emulator_button)
        layout.addWidget(self._emulators_list)
        layout.addWidget(remove_emulator_button)
        layout.addWidget(QLabel("Profile"))
        layout.addWidget(self._sync_profile_button)
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
            # The core is shown because it changes how the game is launched —
            # a config that looks identical but launches differently is worse
            # than a longer line.
            summary = f"{console_name}: {config.executable_path}"
            if config.core_path:
                summary += f"  -L {config.core_path}"
            item = QListWidgetItem(summary)
            item.setData(Qt.ItemDataRole.UserRole, config.console_id)
            self._emulators_list.addItem(item)

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

    def _on_browse_emulator(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Emulator Executable")
        if file_path:
            self._emulator_path_input.setText(file_path)

    def _on_browse_core(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select libretro Core", filter="libretro cores (*.dll *.so *.dylib)"
        )
        if file_path:
            self._emulator_core_input.setText(file_path)

    def _on_save_emulator(self) -> None:
        console_id = self._emulator_console_selector.currentData()
        executable_path = self._emulator_path_input.text().strip()
        if console_id is None or not executable_path:
            QMessageBox.warning(
                self, "Missing info", "Pick a console and an emulator executable."
            )
            return
        arguments_template = self._emulator_args_input.text().strip() or None
        core_path = self._emulator_core_input.text().strip() or None
        library_service.set_emulator_config(
            console_id, executable_path, arguments_template, core_path
        )
        self._emulator_path_input.clear()
        self._emulator_args_input.clear()
        self._emulator_core_input.clear()
        self.refresh()

    def _on_remove_emulator(self) -> None:
        item = self._emulators_list.currentItem()
        if item is None:
            return
        self._remove_emulator(item.data(Qt.ItemDataRole.UserRole))

    def _remove_emulator(self, console_id: int) -> None:
        library_service.remove_emulator_config(console_id)
        self.refresh()

    def _on_sync_profile(self) -> None:
        account = self.app_context.active_account
        if account is None:
            QMessageBox.warning(self, "No account", "Add or select an account first.")
            return

        client = session_service.build_api_client(account)
        self._sync_profile_button.setEnabled(False)
        self._sync_profile_button.setText("Syncing...")

        self._sync_profile_worker = ServiceWorker(sync_service.sync_profile, client, account)
        self._sync_profile_worker.finished_ok.connect(self._on_sync_profile_done)
        self._sync_profile_worker.failed.connect(self._on_sync_profile_failed)
        self._sync_profile_worker.start()

    def _reset_sync_profile_button(self) -> None:
        self._sync_profile_button.setText("Sync Profile")
        self._sync_profile_button.setEnabled(True)

    def _on_sync_profile_done(self, _result: object) -> None:
        self._reset_sync_profile_button()

    def _on_sync_profile_failed(self, message: str) -> None:
        self._reset_sync_profile_button()
        QMessageBox.warning(self, "Sync failed", message)
