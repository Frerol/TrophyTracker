"""Awards view (D7): the displayed account's badges, event awards and events.

Opened from Home's awards panel as a detail screen (`MainWindow.open_detail`),
so Back returns to Home unchanged. Badges were synced but never shown before
(ScreenDataMapping F1). The Events list and the new-events banner moved here
from Home in R19.

Accounts can hold hundreds of awards, so badges use a model/view list that
requests an image only when its row is painted, with a bounded pixmap cache
(the R07 budget), rather than one widget per award.
"""

from collections import OrderedDict
from typing import Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QListView, QPushButton, QScrollArea, QTabWidget, QVBoxLayout,
    QWidget,
)

from retrocheevos.gui import styles
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.components import button, page_title, text_label
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.models.profile import Badge
from retrocheevos.services import events_service, notification_service, profile_service
from retrocheevos.widgets.event_row import EventRow

BADGE_ICON = 64
BADGE_CELL = QSize(132, 112)
# Pixmaps kept per model; ~64 px RGBA icons, about 2 MB.
MAX_CACHED_BADGE_IMAGES = 128
MAX_BANNER_EVENT_NAMES = 3
EMPTY_AWARDS_TEXT = "Sync profile to load awards."
EMPTY_EVENT_AWARDS_TEXT = "No event awards yet."
EMPTY_EVENTS_TEXT = "No events synced yet. Run Sync Everything from the catalog to load them."
NO_ACCOUNT_TEXT = "Choose an account in the sidebar to see its awards."


def _placeholder() -> QPixmap:
    pixmap = QPixmap(BADGE_ICON, BADGE_ICON)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(styles.SURFACE_RAISED))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, BADGE_ICON, BADGE_ICON, styles.RADIUS_COVER, styles.RADIUS_COVER)
    painter.end()
    return pixmap


class BadgeListModel(QAbstractListModel):
    """Badges with lazily loaded, bounded-cache images."""

    def __init__(self, image_loader: ImageLoader, parent=None) -> None:
        super().__init__(parent)
        self._loader = image_loader
        self._badges: list[Badge] = []
        self._rows: dict[int, int] = {}
        self._cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._pending: set[int] = set()
        # Failed downloads are not retried while the view is open.
        self._failed: set[int] = set()
        self._placeholder = _placeholder()
        image_loader.badge_image_ready.connect(self._on_image)

    def set_badges(self, badges: list[Badge]) -> None:
        self.beginResetModel()
        self._badges = list(badges)
        self._rows = {badge.id: row for row, badge in enumerate(self._badges)}
        self.endResetModel()

    def badges(self) -> list[Badge]:
        return list(self._badges)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 — Qt override
        return 0 if parent.isValid() else len(self._badges)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._badges):
            return None
        badge = self._badges[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole,
                    Qt.ItemDataRole.AccessibleTextRole):
            return badge.name
        if role == Qt.ItemDataRole.DecorationRole:
            return self._pixmap_for(badge)
        return None

    def requested_ids(self) -> set[int]:
        return set(self._pending) | set(self._cache) | set(self._failed)

    def _pixmap_for(self, badge: Badge) -> QPixmap:
        if badge.id in self._cache:
            self._cache.move_to_end(badge.id)
            return self._cache[badge.id]
        if badge.id not in self._pending and badge.id not in self._failed:
            self._pending.add(badge.id)
            self._loader.request_badge(badge.id, badge.image_path)
        return self._placeholder

    def _on_image(self, badge_id: int, pixmap: Optional[QPixmap]) -> None:
        if badge_id not in self._pending:
            return
        self._pending.discard(badge_id)
        if pixmap is None or pixmap.isNull():
            self._failed.add(badge_id)
            return
        self._cache[badge_id] = pixmap.scaled(
            BADGE_ICON, BADGE_ICON, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        while len(self._cache) > MAX_CACHED_BADGE_IMAGES:
            self._cache.popitem(last=False)
        row = self._rows.get(badge_id)
        if row is not None:
            index = self.index(row)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])


def _badge_list(model: BadgeListModel, name: str) -> QListView:
    view = QListView()
    view.setModel(model)
    view.setViewMode(QListView.ViewMode.IconMode)
    view.setResizeMode(QListView.ResizeMode.Adjust)
    view.setMovement(QListView.Movement.Static)
    view.setUniformItemSizes(True)
    view.setWordWrap(True)
    view.setIconSize(QSize(BADGE_ICON, BADGE_ICON))
    view.setGridSize(BADGE_CELL)
    view.setSpacing(4)
    view.setSelectionMode(QListView.SelectionMode.NoSelection)
    view.setAccessibleName(name)
    return view


class AwardsView(QWidget):
    back_requested = Signal()
    # Unread events were marked read; Home updates its summary.
    events_read = Signal()

    def __init__(self, app_context: AppContext, image_loader: ImageLoader,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app_context = app_context
        self._image_loader = image_loader

        back = button("‹ Home", "ghost", compact=True)
        back.setToolTip("Back to Home (Alt+Left)")
        back.clicked.connect(self.back_requested)
        self._account_label = text_label("", "secondary")
        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(page_title("Awards"))
        heading.addWidget(self._account_label)
        header = QHBoxLayout()
        header.addLayout(heading)
        header.addStretch(1)

        self._badges_model = BadgeListModel(image_loader, self)
        self._event_awards_model = BadgeListModel(image_loader, self)
        self._badges_view = _badge_list(self._badges_model, "Badges")
        self._event_awards_view = _badge_list(self._event_awards_model, "Event awards")
        self._badges_empty = text_label(EMPTY_AWARDS_TEXT, "secondary", wrap=True)
        self._event_awards_empty = text_label(EMPTY_EVENT_AWARDS_TEXT, "secondary", wrap=True)

        self._banner = QPushButton()
        self._banner.setProperty("variant", "ghost")
        self._banner.setToolTip("Mark these events as read")
        self._banner.clicked.connect(self._mark_events_read)
        self._banner.setVisible(False)
        self._events_container = QWidget()
        self._events_layout = QVBoxLayout(self._events_container)
        self._events_layout.setContentsMargins(0, 0, 0, 0)
        self._events_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        events_scroll = QScrollArea()
        events_scroll.setWidgetResizable(True)
        events_scroll.setWidget(self._events_container)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._tab(self._badges_empty, self._badges_view), "Badges")
        self._tabs.addTab(self._tab(self._event_awards_empty, self._event_awards_view), "Event awards")
        events_tab = QWidget()
        events_layout = QVBoxLayout(events_tab)
        events_layout.addWidget(self._banner, alignment=Qt.AlignmentFlag.AlignLeft)
        events_layout.addWidget(events_scroll, stretch=1)
        self._tabs.addTab(events_tab, "Events")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            styles.PAGE_PADDING_H, styles.PAGE_PADDING_V - 8,
            styles.PAGE_PADDING_H, styles.PAGE_PADDING_V - 8,
        )
        layout.setSpacing(styles.GAP)
        layout.addWidget(back, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(header)
        layout.addWidget(self._tabs, stretch=1)

    @staticmethod
    def _tab(empty_label, view) -> QWidget:
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.addWidget(empty_label)
        tab_layout.addWidget(view, stretch=1)
        return tab

    def refresh(self) -> None:
        account = self.app_context.active_account
        if account is None:
            self._account_label.setText(NO_ACCOUNT_TEXT)
            badges: list[Badge] = []
        else:
            self._account_label.setText(f"Account: {account.username}")
            badges = profile_service.list_badges(account.id)
        regular = [badge for badge in badges if not badge.is_event]
        event_awards = [badge for badge in badges if badge.is_event]
        self._badges_model.set_badges(regular)
        self._event_awards_model.set_badges(event_awards)
        self._badges_view.setVisible(bool(regular))
        self._badges_empty.setVisible(not regular)
        self._badges_empty.setText(EMPTY_AWARDS_TEXT if not badges else "No badges yet.")
        self._event_awards_view.setVisible(bool(event_awards))
        self._event_awards_empty.setVisible(not event_awards)
        self._tabs.setTabText(0, f"Badges ({len(regular)})")
        self._tabs.setTabText(1, f"Event awards ({len(event_awards)})")
        self._refresh_events()

    def _refresh_events(self) -> None:
        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        account = self.app_context.active_account
        if account is None:
            self._banner.setVisible(False)
            self._tabs.setTabText(2, "Events")
            return
        unread = notification_service.list_unread_events(account.id)
        unread_ids = {notification.game_id for notification in unread}
        if unread:
            names = ", ".join(n.message for n in unread[:MAX_BANNER_EVENT_NAMES])
            more = len(unread) - MAX_BANNER_EVENT_NAMES
            suffix = f" and {more} more" if more > 0 else ""
            self._banner.setText(f"{len(unread)} new: {names}{suffix} — mark as read")
        self._banner.setVisible(bool(unread))
        events = events_service.list_events_with_progress(account.id)
        for entry in events:
            self._events_layout.addWidget(
                EventRow(entry, self._image_loader, is_new=entry.game.id in unread_ids)
            )
        if not events:
            self._events_layout.addWidget(text_label(EMPTY_EVENTS_TEXT, "secondary", wrap=True))
        self._tabs.setTabText(2, f"Events ({len(events)})")

    def _mark_events_read(self) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        notification_service.mark_events_read(account.id)
        self._refresh_events()
        self.events_read.emit()

    def event_rows(self) -> list[EventRow]:
        rows = (self._events_layout.itemAt(i).widget() for i in range(self._events_layout.count()))
        return [row for row in rows if isinstance(row, EventRow)]
