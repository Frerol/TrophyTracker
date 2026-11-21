"""Application sidebar: brand, destinations and the displayed account (R18).

The sidebar replaces the pre-revamp top header and navigation row. It only
reports what the user picked (`destination_selected`, `account_chosen`,
`sign_out_requested`); `gui/main_window.py` owns the pages and the session
changes, the same "emit, don't reach into MainWindow" shape the pages use.

The account area shows the account `AppContext` reports as displayed. Saved
credentials never change it on their own: only an explicit choice in its menu
or in Settings does (R01, D-series account rules in ScreenDataMapping §4).
"""

from typing import Optional

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from retrocheevos.gui import styles
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.assets import sized_icon_path
from retrocheevos.gui.components import SidebarItem
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.account import Account
from retrocheevos.services import image_service, profile_service, session_service
from retrocheevos.version import APP_VERSION

DESTINATIONS = (
    ("home", "Home"),
    ("library", "Library"),
    ("lists", "Lists"),
    ("settings", "Settings"),
)

BRAND_ICON_SIZE = 32
AVATAR_SIZE = 40
AVATAR_BORDER = 2
SIDEBAR_MARGIN_H = 14
SIDEBAR_MARGIN_V = 20

DISPLAYED_ACCOUNT_CAPTION = "Displayed account"
NO_ACCOUNT_TITLE = "No account selected"
NO_ACCOUNT_CAPTION = "Choose an account"
SIGN_OUT_TEXT = "Sign out"
DISPLAY_ACCOUNT_TEXT = "Display {name}"
ADD_ACCOUNT_TEXT = "Add an account…"
MANAGE_ACCOUNTS_TEXT = "Manage accounts…"

SHELL_WORKER_PHOTO = ("shell", "photo")


def round_avatar(pixmap: Optional[QPixmap], initial: str, size: int, ratio: float = 1.0) -> QPixmap:
    """A circular avatar with a gold ring; the initial on turquoise when no photo."""
    device = max(1, round(size * ratio))
    canvas = QPixmap(device, device)
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    inner = QRectF(AVATAR_BORDER / 2, AVATAR_BORDER / 2, size - AVATAR_BORDER, size - AVATAR_BORDER)
    clip = QPainterPath()
    clip.addEllipse(inner)
    if pixmap is not None and not pixmap.isNull():
        painter.save()
        painter.setClipPath(clip)
        scaled = pixmap.scaled(
            device, device, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        painter.drawPixmap(0, 0, scaled)
        painter.restore()
    else:
        painter.fillPath(clip, QColor(styles.ACCENT_TURQUOISE))
        font = QFont(styles.FONT_DISPLAY)
        font.setPixelSize(int(size * 0.42))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(styles.TEXT_ON_ACCENT))
        painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, (initial or "?")[:1].upper())
    painter.setPen(QPen(QColor(styles.ACCENT_GOLD), AVATAR_BORDER))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(inner)
    painter.end()
    return canvas


def _brand_icon() -> QIcon:
    icon = QIcon()
    for size in (BRAND_ICON_SIZE, BRAND_ICON_SIZE * 2):
        pixmap = QPixmap(str(sized_icon_path(size)))
        if not pixmap.isNull():
            icon.addPixmap(pixmap)
    return icon


class AccountPanel(QPushButton):
    """The displayed account at the bottom of the sidebar; click opens its menu."""

    account_chosen = Signal(int)
    sign_out_requested = Signal()
    navigate_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("accountPanel")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._account: Optional[Account] = None
        self._photo: Optional[QPixmap] = None
        self._menu: Optional[QMenu] = None

        self._avatar = QLabel()
        self._avatar.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self._name = QLabel()
        self._name.setObjectName("accountName")
        self._caption = QLabel()
        self._caption.setProperty("role", "secondary")
        for label in (self._avatar, self._name, self._caption):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(0)
        text.addWidget(self._name)
        text.addWidget(self._caption)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(self._avatar)
        layout.addLayout(text, stretch=1)
        self.setMinimumHeight(AVATAR_SIZE + 16)

        self.clicked.connect(self.show_menu)
        self.set_account(None)

    def sizeHint(self) -> QSize:  # noqa: N802 — Qt override
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — Qt override
        return QSize(0, AVATAR_SIZE + 16)

    @property
    def account(self) -> Optional[Account]:
        return self._account

    def set_account(self, account: Optional[Account]) -> None:
        self._account = account
        self._photo = None
        if account is None:
            self._name.setText(NO_ACCOUNT_TITLE)
            self._caption.setText(NO_ACCOUNT_CAPTION)
            self.setAccessibleName(f"Account menu: {NO_ACCOUNT_TITLE}")
            self.setToolTip(NO_ACCOUNT_CAPTION)
        else:
            self._name.setText(account.username)
            self._caption.setText(DISPLAYED_ACCOUNT_CAPTION)
            self.setAccessibleName(f"Account menu: {account.username}, {DISPLAYED_ACCOUNT_CAPTION.lower()}")
            self.setToolTip(f"{DISPLAYED_ACCOUNT_CAPTION}: {account.username}")
        self._paint_avatar()

    def set_photo(self, pixmap: Optional[QPixmap]) -> None:
        self._photo = pixmap if pixmap is not None and not pixmap.isNull() else None
        self._paint_avatar()

    def has_photo(self) -> bool:
        return self._photo is not None

    def name_text(self) -> str:
        return self._name.text()

    def _paint_avatar(self) -> None:
        initial = self._account.username if self._account is not None else "?"
        self._avatar.setPixmap(
            round_avatar(self._photo, initial, AVATAR_SIZE, self.devicePixelRatioF())
        )

    def build_menu(self) -> QMenu:
        """The account menu for the current state; separate from showing it for tests."""
        menu = QMenu(self)
        accounts = session_service.list_accounts()
        active = self._account
        if active is not None:
            switch = QMenu(f"{DISPLAYED_ACCOUNT_CAPTION}: {active.username}", menu)
            for account in accounts:
                action = switch.addAction(account.username, self._chooser(account.id))
                action.setCheckable(True)
                action.setChecked(account.id == active.id)
            menu.addMenu(switch)
            menu.addSeparator()
            menu.addAction(MANAGE_ACCOUNTS_TEXT, lambda: self.navigate_requested.emit("settings"))
            menu.addAction(SIGN_OUT_TEXT, self.sign_out_requested.emit)
            return menu
        for account in accounts:
            menu.addAction(DISPLAY_ACCOUNT_TEXT.format(name=account.username), self._chooser(account.id))
        if accounts:
            menu.addSeparator()
        menu.addAction(ADD_ACCOUNT_TEXT, lambda: self.navigate_requested.emit("settings"))
        return menu

    def _chooser(self, account_id: int):
        return lambda: self.account_chosen.emit(account_id)

    def show_menu(self) -> None:
        if self._menu is not None:
            self._menu.close()
        menu = self.build_menu()
        menu.aboutToHide.connect(self._on_menu_hidden)
        self._menu = menu
        # The panel sits at the bottom of the window, so open upwards.
        height = menu.sizeHint().height()
        menu.popup(self.mapToGlobal(QPoint(0, -height)))

    def _on_menu_hidden(self) -> None:
        self._menu = None


class Sidebar(QFrame):
    """Brand, the four destinations, the displayed account and the version."""

    destination_selected = Signal(str)

    def __init__(self, app_context: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(styles.SIDEBAR_WIDTH)
        self.app_context = app_context
        self._photo_generation = 0
        self._photo_account_id: Optional[int] = None

        icon = QLabel()
        icon.setObjectName("sidebarBrandIcon")
        icon.setPixmap(_brand_icon().pixmap(BRAND_ICON_SIZE, BRAND_ICON_SIZE))
        icon.setFixedSize(BRAND_ICON_SIZE, BRAND_ICON_SIZE)
        icon.setAccessibleName("TrophyTracker")
        name = QLabel("TrophyTracker")
        name.setObjectName("sidebarBrand")
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        brand.addWidget(icon)
        brand.addWidget(name, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SIDEBAR_MARGIN_H, SIDEBAR_MARGIN_V, SIDEBAR_MARGIN_H, SIDEBAR_MARGIN_V)
        layout.setSpacing(4)
        layout.addLayout(brand)
        layout.addSpacing(styles.SPACE_L)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.items: dict[str, SidebarItem] = {}
        self.shortcuts: dict[str, QShortcut] = {}
        for index, (key, title) in enumerate(DESTINATIONS, start=1):
            item = SidebarItem(title)
            sequence = QKeySequence(f"Ctrl+{index}")
            item.setToolTip(f"{title} ({sequence.toString(QKeySequence.SequenceFormat.NativeText)})")
            item.clicked.connect(lambda _checked=False, k=key: self.destination_selected.emit(k))
            self._group.addButton(item)
            self.items[key] = item
            layout.addWidget(item)
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda k=key: self.destination_selected.emit(k))
            self.shortcuts[key] = shortcut

        layout.addStretch(1)
        self.account_panel = AccountPanel()
        layout.addWidget(self.account_panel)
        layout.addSpacing(styles.SPACE_S)
        self.version_label = QLabel(f"v{APP_VERSION}")
        self.version_label.setObjectName("versionBadge")
        self.version_label.setAccessibleName(f"TrophyTracker version {APP_VERSION}")
        footer = QHBoxLayout()
        footer.setContentsMargins(6, 0, 0, 0)
        footer.addWidget(self.version_label)
        footer.addStretch(1)
        layout.addLayout(footer)

    def set_current(self, key: str) -> None:
        item = self.items[key]
        if not item.isChecked():
            item.setChecked(True)

    def current(self) -> Optional[str]:
        return next((key for key, item in self.items.items() if item.isChecked()), None)

    # Account and avatar -------------------------------------------------

    def set_account(self, account: Optional[Account]) -> None:
        """Show `account` and drop any avatar request for a previous one (R01)."""
        self._photo_generation += 1
        self.app_context.workers.cancel_key(self._photo_key(self._photo_generation - 1))
        self._photo_account_id = None
        self.account_panel.set_account(account)
        self.refresh_avatar()

    def refresh_avatar(self) -> None:
        """Load the profile photo once it is known; cheap when already loaded."""
        account = self.account_panel.account
        if account is None or self._photo_account_id == account.id:
            return
        if self.app_context._shutting_down:
            return
        key = self._photo_key(self._photo_generation)
        if self.app_context.workers.has_key(key):
            return
        stats = profile_service.get_profile_stats(account.id)
        if stats is None:
            return
        generation, account_id = self._photo_generation, account.id
        worker = ServiceWorker(image_service.ensure_user_pic_cached, account.username, stats.user_pic_path)
        worker.finished_ok.connect(
            lambda path: self._on_photo_ready_guarded(path, generation, account_id)
        )
        self.app_context.workers.start(worker, key=key)

    def _photo_key(self, generation: int) -> tuple:
        return (*SHELL_WORKER_PHOTO, generation)

    def _on_photo_ready_guarded(self, cached_path, generation: int, account_id: int) -> None:
        if generation != self._photo_generation:
            return
        account = self.app_context.active_account
        if account is None or account.id != account_id:
            return
        self._on_photo_ready(cached_path, account_id)

    def _on_photo_ready(self, cached_path, account_id: int) -> None:
        # `None` means no photo yet or a failed download; the initial stays.
        if not cached_path:
            return
        pixmap = QPixmap(str(cached_path))
        if pixmap.isNull():
            return
        self._photo_account_id = account_id
        self.account_panel.set_photo(pixmap)
