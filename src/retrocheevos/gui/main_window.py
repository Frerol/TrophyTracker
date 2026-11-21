"""Main window: the sidebar, the destination pages and detail routes (R18)."""

import time

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.awards_view import AwardsView
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.pages.home_page import HomePage
from retrocheevos.gui.pages.library_page import LibraryPage
from retrocheevos.gui.pages.lists_page import ListsPage
from retrocheevos.gui.pages.settings_page import SettingsPage
from retrocheevos.gui.sidebar import Sidebar
from retrocheevos.gui.workers import SHUTDOWN_TIMEOUT_MS, ServiceWorker
from retrocheevos.services import preferences_service, session_service, update_service
from retrocheevos.widgets.update_banner import UpdateBanner

# Smallest supported window (ScreenDataMapping §6); every action stays
# reachable at this size.
MINIMUM_WIDTH = 1024
MINIMUM_HEIGHT = 720


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TrophyTracker")
        # No `setWindowIcon` here on purpose: `main.py::_build_app_icon`
        # builds the multi-resolution icon and sets it on both the
        # QApplication and this window. This used to set a single-pixmap
        # `QIcon(ICON_PATH)` too, which won until main.py overwrote it — a
        # race with no upside and a plausible cause of the icon showing
        # inconsistently.
        self.resize(
            preferences_service.get_int(preferences_service.KEY_WINDOW_WIDTH, 1200),
            preferences_service.get_int(preferences_service.KEY_WINDOW_HEIGHT, 800),
        )

        self.app_context = AppContext()
        self._close_deadline = 0.0
        self._close_retry_timer = QTimer(self)
        self._close_retry_timer.setSingleShot(True)
        self._close_retry_timer.setInterval(25)
        self._close_retry_timer.timeout.connect(self.close)

        # The four persistent destinations. Each page is built once and kept,
        # so its search, filters, selection and scroll survive navigation.
        self._destinations: dict[str, Page] = {
            "home": HomePage(self.app_context),
            "library": LibraryPage(self.app_context),
            "lists": ListsPage(self.app_context),
            "settings": SettingsPage(self.app_context),
        }
        self._current_key = "home"
        # Open detail screens, most recent last, each with the destination it
        # was opened from. Details are contextual: they never replace a
        # destination and are dropped when the user picks one in the sidebar.
        self._detail_stack: list[tuple[QWidget, str]] = []

        # Nothing else listened to this once: signing in from Settings left
        # the other pages on the previous session until a restart.
        self.app_context.active_account_changed.connect(self._on_active_account_changed)

        self._sidebar = Sidebar(self.app_context)
        self._sidebar.destination_selected.connect(self._on_destination_selected)
        account_panel = self._sidebar.account_panel
        account_panel.account_chosen.connect(self._on_login)
        account_panel.sign_out_requested.connect(self._on_logout)
        account_panel.navigate_requested.connect(self.navigate)
        self._sidebar.set_account(self.app_context.active_account)
        home = self._destinations["home"]
        home.profile_updated.connect(self._sidebar.refresh_avatar)
        home.navigate_requested.connect(self.navigate)
        home.awards_requested.connect(self.open_awards)
        # Created on first use and shared by every Awards view, so repeated
        # visits reuse one registered loader (shutdown waits for it).
        self._awards_image_loader = None

        self._pages = QStackedWidget()
        self._pages.setObjectName("pages")
        for page in self._destinations.values():
            self._pages.addWidget(page)

        back = QShortcut(QKeySequence(QKeySequence.StandardKey.Back), self)
        back.activated.connect(self.go_back)
        self._back_shortcut = back

        # Above the content rather than inside a page: it's about the app
        # itself, not about whatever you happen to be looking at. Starts
        # hidden, so it costs no space until there is something to say.
        self._update_banner = UpdateBanner()
        self._update_banner.dismissed.connect(self._on_update_dismissed)
        # What the banner is currently advertising, so dismissing it can
        # record *which* version was dismissed.
        self._available_update = None

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._update_banner)
        content_layout.addWidget(self._pages, stretch=1)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar)
        layout.addWidget(content, stretch=1)
        self.setCentralWidget(central)
        self.setMinimumSize(MINIMUM_WIDTH, MINIMUM_HEIGHT)

        self.navigate("home")
        self._restore_window_state()
        self._start_update_check()

    def _start_update_check(self) -> None:
        """Ask GitHub whether there's a newer release, off the UI thread.

        Held on `self` because a `QThread` that goes out of scope is
        destroyed while still running — Qt aborts the process for that, and
        it would happen at startup, on every launch.

        `failed` is deliberately not connected. Every expected "no" already
        comes back as a None result (`update_service.check_for_update`), so
        anything reaching `failed` is a genuine surprise the user can do
        nothing about — and a dialog on launch about a *version check* is far
        worse than the silence.
        """
        self._update_worker = ServiceWorker(update_service.check_for_update)
        self._update_worker.finished_ok.connect(self._on_update_check_finished)
        self._update_worker.start()
        # register
        self.app_context.workers.start(self._update_worker, key=("main", "update-check"))

    def _on_update_check_finished(self, available) -> None:
        if available is None:
            return
        dismissed = preferences_service.get_str(
            preferences_service.KEY_DISMISSED_UPDATE_VERSION
        )
        if not update_service.should_notify(available.version, dismissed):
            return
        self._available_update = available
        self._update_banner.show_update(available.version, available.url)

    def _on_update_dismissed(self) -> None:
        """Remember *which* version was waved away, not that one was.

        `preferences_service.set_str` is a no-op with no active account, and
        this check runs before anyone has necessarily signed in — so a
        dismissal made on the login screen hides the banner for this session
        only and it returns next launch. Deliberately not worked around:
        preferences are per-account throughout, and inventing a second,
        account-less store for this one value would be a bigger change than
        the annoyance justifies. It resolves itself the moment they sign in.
        """
        if self._available_update is None:
            return
        preferences_service.set_str(
            preferences_service.KEY_DISMISSED_UPDATE_VERSION,
            self._available_update.version,
        )

    def _restore_window_state(self) -> None:
        """Fullscreen wins over maximized, since a window can be flagged both
        and only one of them is what the user last saw. The plain size set in
        `__init__` is what a restored window falls back to."""
        if preferences_service.get_bool(preferences_service.KEY_WINDOW_FULLSCREEN, False):
            self.showFullScreen()
        elif preferences_service.get_bool(preferences_service.KEY_WINDOW_MAXIMIZED, False):
            self.showMaximized()
        else:
            # Explicit, so signing into an account that was last plain-windowed
            # actually leaves fullscreen rather than inheriting the previous
            # session's state.
            self.showNormal()
            self.resize(
                preferences_service.get_int(preferences_service.KEY_WINDOW_WIDTH, 1200),
                preferences_service.get_int(preferences_service.KEY_WINDOW_HEIGHT, 800),
            )

    def changeEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Persist window state the moment it changes, not only on close.

        Saving at close alone lost everything if you logged out first: with
        no active account `preferences_service` drops writes, so the whole
        session's state went with it. Saving while signed in means logging
        out never discards anything that was already true.
        """
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._save_window_state()

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self._save_window_state()

    def _save_window_state(self) -> None:
        """`normalGeometry()`, not the current size: a maximized window
        reports the screen's, so saving that would make "restore down"
        produce a window the size of the display with no way back."""
        preferences_service.set_bool(
            preferences_service.KEY_WINDOW_FULLSCREEN, self.isFullScreen()
        )
        preferences_service.set_bool(
            preferences_service.KEY_WINDOW_MAXIMIZED, self.isMaximized()
        )
        normal = self.normalGeometry()
        if normal.width() > 0 and normal.height() > 0:
            preferences_service.set_int(
                preferences_service.KEY_WINDOW_WIDTH, normal.width()
            )
            preferences_service.set_int(
                preferences_service.KEY_WINDOW_HEIGHT, normal.height()
            )

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Saves window state on the way out.

        A last write for the case where nothing changed since the previous
        one — `changeEvent`/`resizeEvent` do the real work.

        Closing does not block the event loop: cancellation is requested and
        the close is retried until background work drains, so delayed results
        are delivered (and discarded) before the window goes away. The wait is
        bounded by `SHUTDOWN_TIMEOUT_MS`; work still running after that is
        kept referenced by the registry instead of holding the app open.
        """
        if not self.app_context._shutting_down:
            self._save_window_state()
            self._close_deadline = time.monotonic() + SHUTDOWN_TIMEOUT_MS / 1000
        self.app_context.begin_shutdown()
        if (
            not self.app_context.is_idle()
            and time.monotonic() < self._close_deadline
        ):
            event.ignore()
            self.setEnabled(False)
            self._close_retry_timer.start()
            return
        super().closeEvent(event)

    # Navigation ----------------------------------------------------------

    def current_destination(self) -> str:
        return self._current_key

    def destination(self, key: str) -> Page:
        return self._destinations[key]

    def navigate(self, key: str) -> None:
        """Show destination `key`, closing any open detail.

        `refresh()` reloads the page's data; pages keep their own view state
        (search, filters, selection, scroll) across it.
        """
        self._close_details()
        page = self._destinations[key]
        self._current_key = key
        self._pages.setCurrentWidget(page)
        self._sidebar.set_current(key)
        page.refresh()
        self._sidebar.refresh_avatar()

    def _on_destination_selected(self, key: str) -> None:
        # Picking the destination already on screen returns it to its root
        # view (Home: collapse catalog results), like most sidebars do.
        if key == self._current_key and not self._detail_stack:
            reset = getattr(self._destinations[key], "reset_to_root", None)
            if reset is not None:
                reset()
            self._sidebar.set_current(key)
            return
        self.navigate(key)

    def open_detail(self, widget: QWidget) -> None:
        """Show a contextual detail screen opened from the current view.

        The originating destination stays selected in the sidebar, and
        `go_back()` returns to it without refreshing, so its state is intact.
        """
        self._detail_stack.append((widget, self._current_key))
        self._pages.addWidget(widget)
        self._pages.setCurrentWidget(widget)

    def open_awards(self) -> AwardsView:
        """Open the Awards view (D7) on top of the current destination."""
        if self._awards_image_loader is None:
            self._awards_image_loader = self.app_context.create_image_loader()
        view = AwardsView(self.app_context, self._awards_image_loader)
        view.back_requested.connect(self.go_back)
        view.events_read.connect(self._destinations["home"]._refresh_awards_summary)
        self.open_detail(view)
        view.refresh()
        return view

    def go_back(self) -> bool:
        """Close the top detail screen. Returns False when there is none."""
        if not self._detail_stack:
            return False
        widget, origin = self._detail_stack.pop()
        below = self._detail_stack[-1][0] if self._detail_stack else self._destinations[origin]
        self._pages.setCurrentWidget(below)
        self._discard_detail(widget)
        self._sidebar.set_current(origin)
        return True

    def detail_open(self) -> bool:
        return bool(self._detail_stack)

    def _close_details(self) -> None:
        while self._detail_stack:
            widget, _origin = self._detail_stack.pop()
            self._discard_detail(widget)

    def _discard_detail(self, widget: QWidget) -> None:
        self._pages.removeWidget(widget)
        widget.deleteLater()

    # Session -------------------------------------------------------------

    def _on_active_account_changed(self, account) -> None:
        """Show whoever is now displayed, without changing destination.

        Only the visible page is refreshed; the others refresh themselves on
        their way in (`navigate`). Details and Home's catalog search belong
        to the previous account's view, so they are closed.
        """
        # Deliberately does not touch the window geometry: the window is the
        # user's current context, not account data.
        self._sidebar.set_account(account)
        if self._detail_stack:
            self._close_details()
            self._pages.setCurrentWidget(self._destinations[self._current_key])
            self._sidebar.set_current(self._current_key)
        self._destinations["home"].reset_to_root()
        current = self._pages.currentWidget()
        if current is not None:
            current.refresh()

    def _on_login(self, account_id: int) -> None:
        """Display a saved account chosen from the sidebar account menu."""
        try:
            session_service.switch_account(account_id)
        except ValueError as error:
            QMessageBox.warning(self, "Account unavailable", str(error))
            return
        self.app_context.refresh_active_account()
        self.navigate("home")

    def _on_logout(self) -> None:
        session_service.logout()
        self.app_context.refresh_active_account()
        self.navigate("home")
