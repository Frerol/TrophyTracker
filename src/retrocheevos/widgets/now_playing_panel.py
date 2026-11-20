"""A live, account-safe current-game panel with bounded background refreshes."""

import time
from datetime import timezone
from threading import Event
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QTabWidget, QVBoxLayout,
)

from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.account import Account
from retrocheevos.models.now_playing import NowPlayingSnapshot
from retrocheevos.services import now_playing_service

REFRESH_INTERVAL_MS = 60_000
MAX_RETRY_INTERVAL_MS = 900_000
ACHIEVEMENT_LIST_HEIGHT = 110


class NowPlayingPanel(QGroupBox):
    progress_updated = Signal()

    def __init__(self) -> None:
        super().__init__('Now Playing')
        self._account: Optional[Account] = None
        self._worker: Optional[ServiceWorker] = None
        self._generation = 0
        self._worker_generation = 0
        self._last_attempt: Optional[float] = None
        self._interval = REFRESH_INTERVAL_MS
        self._snapshot: Optional[NowPlayingSnapshot] = None
        self._signature = None
        self._pending_refresh = False
        self._cancel = Event()
        QApplication.instance().aboutToQuit.connect(self._shutdown)
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval)
        self._timer.timeout.connect(self.refresh_progress)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self._title = QLabel('Select an account to track achievements.')
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setWordWrap(True)
        self._title.setStyleSheet('font-weight: bold;')
        top.addWidget(self._title, stretch=1)
        self._refresh_button = QPushButton('Refresh progress')
        self._refresh_button.clicked.connect(lambda: self.refresh_progress(force=True))
        top.addWidget(self._refresh_button)
        layout.addLayout(top)
        self._presence = QLabel()
        self._presence.setTextFormat(Qt.TextFormat.PlainText)
        self._presence.setWordWrap(True)
        layout.addWidget(self._presence)
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        layout.addWidget(self._progress)
        self._counts = QLabel()
        layout.addWidget(self._counts)
        self._unlock_banner = QLabel()
        self._unlock_banner.setTextFormat(Qt.TextFormat.PlainText)
        self._unlock_banner.setWordWrap(True)
        self._unlock_banner.setStyleSheet('color: #cc9900; font-weight: bold;')
        layout.addWidget(self._unlock_banner)
        self._tabs = QTabWidget()
        self._locked = QListWidget()
        self._unlocked = QListWidget()
        self._tabs.addTab(self._locked, 'Locked')
        self._tabs.addTab(self._unlocked, 'Unlocked')
        self._tabs.setMaximumHeight(ACHIEVEMENT_LIST_HEIGHT)
        layout.addWidget(self._tabs)
        self._status = QLabel()
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._clear()

    def set_account(self, account: Optional[Account]) -> None:
        identity = (account.id, account.username, account.api_key) if account else None
        old = (self._account.id, self._account.username, self._account.api_key) if self._account else None
        self._account = account
        if identity != old:
            self._cancel.set()
            self._generation += 1
            self._last_attempt = None
            self._interval = REFRESH_INTERVAL_MS
            self._timer.setInterval(self._interval)
            self._clear()
            self._pending_refresh = self._worker is not None
        self._refresh_button.setEnabled(account is not None and self._worker is None)
        self.refresh_progress()

    def _clear(self) -> None:
        self._snapshot = None
        self._signature = None
        self._locked.clear()
        self._unlocked.clear()
        self._progress.hide()
        self._tabs.hide()
        self._presence.clear()
        self._presence.hide()
        self._counts.clear()
        self._unlock_banner.clear()
        self._unlock_banner.hide()
        self._status.clear()
        self._title.setText('Checking current game...' if self._account else 'Select an account to track achievements.')

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._timer.start()
        self.refresh_progress()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def refresh_progress(self, force: bool = False) -> None:
        if self._account is None or not self.isVisible() or self.window().isMinimized():
            return
        if self._worker is not None:
            if force:
                self._pending_refresh = True
            return
        if not force and self._last_attempt is not None:
            if (time.monotonic() - self._last_attempt) * 1000 < self._interval:
                return
        self._last_attempt = time.monotonic()
        self._worker_generation = self._generation
        self._cancel.clear()
        self._refresh_button.setEnabled(False)
        self._status.setText('Updating from RetroAchievements...')
        self._worker = ServiceWorker(
            now_playing_service.refresh_now_playing, self._account,
            stop_requested=self._cancel.is_set,
        )
        self._worker.finished_ok.connect(self._on_result)
        self._worker.failed.connect(self._on_error)
        self._worker.finished.connect(self._thread_finished)
        self._worker.start()

    def _on_result(self, snapshot: Optional[NowPlayingSnapshot]) -> None:
        if self._worker_generation != self._generation or self._account is None:
            return
        if snapshot is None or snapshot.account_id != self._account.id:
            return
        self._interval = REFRESH_INTERVAL_MS
        self._timer.setInterval(self._interval)
        previous = self._snapshot
        old_unlocks = {
            (item.id, item.hardcore) for item in previous.achievements if item.unlocked_at
        } if previous and previous.game_id == snapshot.game_id else None
        fresh = [item.title for item in snapshot.achievements
                 if item.unlocked_at and old_unlocks is not None
                 and (item.id, item.hardcore) not in old_unlocks]
        if fresh:
            self._unlock_banner.setText('Unlocked: ' + ', '.join(fresh[:3]))
        elif previous is None or previous.game_id != snapshot.game_id:
            self._unlock_banner.clear()
        self._unlock_banner.setVisible(bool(self._unlock_banner.text()) and snapshot.active)
        self._snapshot = snapshot
        prefix = 'Playing' if snapshot.source == 'local' else 'Recent RA activity'
        self._title.setText(f'{prefix}: {snapshot.title}' if snapshot.active else 'No active game detected')
        self._presence.setText(snapshot.presence if snapshot.active else '')
        self._presence.setVisible(bool(snapshot.presence) and snapshot.active)
        achievements = snapshot.achievements
        unlocked = [item for item in achievements if item.unlocked_at is not None]
        total = len(achievements)
        self._progress.setVisible(snapshot.active and total > 0)
        self._tabs.setVisible(snapshot.active and total > 0)
        self._progress.setValue(round(1000 * len(unlocked) / total) if total else 0)
        self._progress.setFormat(f'{len(unlocked)}/{total} achievements — {100 * len(unlocked) / total:.1f}%' if total else '')
        self._counts.setText(
            f'{sum(item.points for item in unlocked)}/{sum(item.points for item in achievements)} points'
            f' · {sum(item.hardcore for item in unlocked)} Hardcore'
            if snapshot.active and total else ''
        )
        signature = (snapshot.game_id, tuple(
            (item.id, item.title, item.description, item.points, item.unlocked_at, item.hardcore)
            for item in achievements
        ))
        if signature != self._signature:
            self._signature = signature
            for widget, entries in (
                (self._locked, [item for item in achievements if item.unlocked_at is None]),
                (self._unlocked, sorted(unlocked, key=lambda item: item.unlocked_at.replace(tzinfo=item.unlocked_at.tzinfo or timezone.utc).timestamp(), reverse=True)),
            ):
                scroll = widget.verticalScrollBar().value()
                widget.clear()
                for achievement in entries:
                    mode = ' · Hardcore' if achievement.hardcore else ''
                    row = QListWidgetItem(f'{achievement.title} · {achievement.points} pts{mode}')
                    row.setToolTip(achievement.description)
                    widget.addItem(row)
                widget.verticalScrollBar().setValue(scroll)
            self._tabs.setTabText(0, f'Locked ({total - len(unlocked)})')
            self._tabs.setTabText(1, f'Unlocked ({len(unlocked)})')
            self.progress_updated.emit()
        time_text = snapshot.checked_at.astimezone().strftime('%H:%M:%S') if snapshot.checked_at else ''
        self._status.setText(snapshot.notice or f'Updated {time_text} · automatic refresh every minute')

    def _on_error(self, message: str) -> None:
        if self._worker_generation != self._generation:
            return
        self._interval = min(self._interval * 2, MAX_RETRY_INTERVAL_MS)
        self._timer.setInterval(self._interval)
        self._status.setText(f'Could not refresh: {message}. Retrying in {self._interval // 60_000} min.')

    def _thread_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._refresh_button.setEnabled(self._account is not None)
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh_progress(force=True)

    def _shutdown(self) -> None:
        self._timer.stop()
        self._cancel.set()
        if self._worker is not None:
            # Each HTTP call has a timeout; stop between calls, and keep the
            # QThread alive until it exits instead of destroying it mid-run.
            self._worker.wait()
