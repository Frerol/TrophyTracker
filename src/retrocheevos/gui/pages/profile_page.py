"""Profile page (UI.md 3.4) — stats, badges, and a manual sync action.

Sync runs on a background thread via `ServiceWorker` — it hits the network
(CodingStandards' threading model forbids that on the UI thread).
"""

from PySide6.QtWidgets import QLabel, QListWidget, QMessageBox, QPushButton, QVBoxLayout

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.services import profile_service, session_service, sync_service


class ProfilePage(Page):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._worker: ServiceWorker | None = None

        self._stats_label = QLabel("No account selected.")
        self._stats_label.setWordWrap(True)
        self._sync_button = QPushButton("Sync Profile")
        self._sync_button.clicked.connect(self._on_sync)

        self._badges_list = QListWidget()

        layout = QVBoxLayout(self)
        layout.addWidget(self._stats_label)
        layout.addWidget(self._sync_button)
        layout.addWidget(QLabel("Badges"))
        layout.addWidget(self._badges_list)
        layout.addStretch(1)

    def refresh(self) -> None:
        account = self.app_context.active_account
        if account is None:
            self._stats_label.setText("No account selected.")
            self._sync_button.setEnabled(False)
            self._badges_list.clear()
            return

        self._sync_button.setEnabled(True)
        stats = profile_service.get_profile_stats(account.id)
        if stats is None:
            self._stats_label.setText(f"{account.username}: no synced stats yet.")
        else:
            self._stats_label.setText(
                f"{account.username} — {stats.points} pts ({stats.hardcore_points} hardcore)\n"
                f"Beaten: {stats.games_beaten}  |  Mastered: {stats.games_mastered}  |  "
                f"Completion: {stats.completion_percentage:.1f}%"
            )

        self._badges_list.clear()
        for badge in profile_service.get_badges(account.id):
            self._badges_list.addItem(badge.name)

    def _on_sync(self) -> None:
        account = self.app_context.active_account
        if account is None:
            return

        client = session_service.build_api_client(account)
        self._sync_button.setEnabled(False)
        self._sync_button.setText("Syncing...")

        self._worker = ServiceWorker(sync_service.sync_profile, client, account)
        self._worker.finished_ok.connect(self._on_sync_done)
        self._worker.failed.connect(self._on_sync_failed)
        self._worker.start()

    def _on_sync_done(self, _result: object) -> None:
        self._sync_button.setText("Sync Profile")
        self._sync_button.setEnabled(True)
        self.refresh()

    def _on_sync_failed(self, message: str) -> None:
        self._sync_button.setText("Sync Profile")
        self._sync_button.setEnabled(True)
        QMessageBox.warning(self, "Sync failed", message)
