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
    QDialog,
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
from retrocheevos.gui.dialogs.find_emulator_dialog import FindEmulatorDialog
from retrocheevos.gui.delegates.removable_list_delegate import RemovableListDelegate
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.selection import selected_item
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.emulator_config import EmulatorConfig
from retrocheevos.widgets.console_selector import ConsoleSelector
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
        self._emulator_configs: dict[int, EmulatorConfig] = {}
        self._flatpak_app_id: Optional[str] = None
        self._flatpak_installation: Optional[str] = None

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

        self._emulator_console_selector = ConsoleSelector()
        self._emulator_path_input = QLineEdit()
        self._emulator_path_input.setPlaceholderText("Path to emulator executable")
        self._emulator_path_input.textEdited.connect(
            lambda _text: self._set_flatpak_selection(None, None)
        )
        self._emulator_flatpak_info = QLabel()
        self._emulator_flatpak_info.setWordWrap(True)
        self._emulator_flatpak_info.hide()
        browse_emulator_button = QPushButton("Browse...")
        browse_emulator_button.clicked.connect(self._on_browse_emulator)
        find_emulator_button = QPushButton("Find...")
        find_emulator_button.clicked.connect(self._on_find_emulator)
        emulator_path_row = QHBoxLayout()
        emulator_path_row.addWidget(self._emulator_path_input)
        emulator_path_row.addWidget(browse_emulator_button)
        emulator_path_row.addWidget(find_emulator_button)

        self._emulator_args_input = QLineEdit()
        self._emulator_args_input.setPlaceholderText(
            'Optional arguments, e.g. --fullscreen "{rom_path}"'
        )

        save_emulator_button = QPushButton("Save Emulator")
        save_emulator_button.clicked.connect(self._on_save_emulator)

        # RetroArch and other libretro frontends are one executable plus a
        # core `.dll` per system, so "the emulator for this console" needs
        # two paths. Optional: emulators with a real per-console binary
        # leave it empty and nothing changes for them.
        self._emulator_core_input = QLineEdit()
        self._emulator_core_input.setPlaceholderText(
            "Optional libretro core (.dll on Windows, .so on Linux)"
        )
        browse_core_button = QPushButton("Browse...")
        browse_core_button.clicked.connect(self._on_browse_core)
        emulator_core_row = QHBoxLayout()
        emulator_core_row.addWidget(self._emulator_core_input)
        emulator_core_row.addWidget(browse_core_button)

        emulator_form = QFormLayout()
        emulator_form.addRow("Console", self._emulator_console_selector)
        emulator_form.addRow("Executable", emulator_path_row)
        emulator_form.addRow(self._emulator_flatpak_info)
        emulator_form.addRow("Core", emulator_core_row)
        emulator_form.addRow("Arguments", self._emulator_args_input)

        self._emulators_list = QListWidget()
        self._emulator_console_selector.currentIndexChanged.connect(self._load_selected_emulator)
        self._emulators_list.currentItemChanged.connect(self._on_emulator_selected)
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

        consoles = console_service.list_configurable_consoles()
        self._emulator_configs = {
            config.console_id: config for config in library_service.list_emulator_configs()
        }
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
        for config in self._emulator_configs.values():
            console_name = console_names.get(config.console_id, f"Console #{config.console_id}")
            # The core is shown because it changes how the game is launched —
            # a config that looks identical but launches differently is worse
            # than a longer line.
            summary = f"{console_name}: {config.executable_path}"
            if config.flatpak_app_id:
                summary = (
                    f"{console_name}: Flatpak {config.flatpak_app_id} "
                    f"({config.flatpak_installation or 'automatic'})"
                )
            if config.core_path:
                summary += f"  -L {config.core_path}"
            item = QListWidgetItem(summary)
            item.setData(Qt.ItemDataRole.UserRole, config.console_id)
            self._emulators_list.addItem(item)
        self._load_selected_emulator()

    def _load_selected_emulator(self) -> None:
        config = self._emulator_configs.get(self._emulator_console_selector.currentData())
        self._emulator_path_input.setText(config.executable_path if config else "")
        self._emulator_args_input.setText((config.arguments_template or "") if config else "")
        self._emulator_core_input.setText((config.core_path or "") if config else "")
        self._set_flatpak_selection(
            config.flatpak_app_id if config else None,
            config.flatpak_installation if config else None,
        )

    def _set_flatpak_selection(
        self, app_id: Optional[str], installation: Optional[str]
    ) -> None:
        self._flatpak_app_id = app_id
        self._flatpak_installation = installation if app_id else None
        self._emulator_flatpak_info.setVisible(bool(app_id))
        self._emulator_flatpak_info.setText(
            f"Flatpak: {app_id} ({installation or 'automatic'}). "
            "ROMs must be accessible to this Flatpak. "
            "For RetroArch, use a core installed for its Flatpak version."
            if app_id else ""
        )

    def _on_emulator_selected(
        self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
    ) -> None:
        if current is None:
            return
        index = self._emulator_console_selector.findData(current.data(Qt.ItemDataRole.UserRole))
        if index >= 0:
            self._emulator_console_selector.setCurrentIndex(index)
            self._load_selected_emulator()

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
        item = selected_item(self._accounts_list)
        if item is None:
            QMessageBox.information(
                self,
                "No account selected",
                "Select an account in the list first, then press Switch to Selected.",
            )
            return
        session_service.switch_account(item.data(Qt.ItemDataRole.UserRole))
        self.app_context.refresh_active_account()
        self.refresh()

    def _on_remove_account(self) -> None:
        item = selected_item(self._accounts_list)
        if item is None:
            # Said out loud rather than returning silently: the old silent
            # return is exactly what made this look broken.
            QMessageBox.information(
                self,
                "No account selected",
                "Select an account in the list first, then press Remove Selected.",
            )
            return

        account_id = item.data(Qt.ItemDataRole.UserRole)
        # Spelled out, because this is now genuinely destructive. Until the
        # foreign keys were handled, removing an account with data attached
        # failed outright — the crash was accidentally acting as a guard.
        # Now it succeeds, so the guard has to be a real one.
        counts = session_service.count_account_data(account_id)
        if counts:
            detail = "\n".join(f"  • {total} {label}" for label, total in counts.items())
            body = (
                f"Remove {item.text()}?\n\nThis permanently deletes:\n{detail}\n\n"
                "The ROM files on disk are not touched. This cannot be undone."
            )
        else:
            body = f"Remove {item.text()}?\n\nThis account has no data stored yet."

        confirmed = QMessageBox.question(
            self,
            "Remove account",
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        session_service.remove_account(account_id)
        self.app_context.refresh_active_account()
        self.refresh()

    def _on_browse_emulator(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Emulator Executable")
        if file_path:
            self._set_flatpak_selection(None, None)
            self._emulator_path_input.setText(file_path)

    def _on_find_emulator(self) -> None:
        console_id = self._emulator_console_selector.currentData()
        if console_id is None:
            QMessageBox.information(self, "No console selected", "Pick a console first.")
            return
        dialog = FindEmulatorDialog(
            console_id, self._emulator_console_selector.currentText(), self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_candidate is not None:
            candidate = dialog.selected_candidate
            if not candidate.requires_core or candidate.flatpak_app_id != self._flatpak_app_id:
                self._emulator_core_input.clear()
            self._emulator_path_input.setText(candidate.executable_path)
            self._set_flatpak_selection(candidate.flatpak_app_id, candidate.flatpak_installation)

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
            console_id, executable_path, arguments_template, core_path,
            flatpak_app_id=self._flatpak_app_id,
            flatpak_installation=self._flatpak_installation,
        )
        self._emulator_path_input.clear()
        self._emulator_args_input.clear()
        self._emulator_core_input.clear()
        self.refresh()

    def _on_remove_emulator(self) -> None:
        item = selected_item(self._emulators_list)
        if item is None:
            QMessageBox.information(
                self,
                "No emulator selected",
                "Select an emulator in the list first, then press Remove.",
            )
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
