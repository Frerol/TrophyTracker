"""Main application window and navigation (UI.md §2).

Home is the root page; everything else is reached from `HomePage`'s user
menu (`_menu_pages`, keyed by the string each menu action emits). Dashboard
was retired once Home (`gui/pages/home_page.py`) fully absorbed its content
(Continue Playing, Recent Activity), and the primary nav list went the same
way once "Home" was its only remaining entry.

The back/forward arrows went too, along with the `_history`/`_history_index`
bookkeeping that existed only to serve them: with four destinations, all of
them one hover away on the user menu (which now includes Home), a browser
history was more chrome than the navigation it described. `_show_page` is
just a page switch again.

The shared header (`HomePage.header_widget`) sits above the page stack, so
it shows on every page rather than only on Home.
"""

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.home_page import HomePage
from retrocheevos.gui.pages.library_page import LibraryPage
from retrocheevos.gui.pages.lists_page import ListsPage
from retrocheevos.gui.pages.settings_page import SettingsPage
from retrocheevos.services import preferences_service, session_service

# Snug: the header already carries its own side margins, and the page below
# has its own. Anything more here reads as dead space at the top of every
# screen — which is exactly what the removed arrow row had become.
WINDOW_MARGIN = 0
HEADER_GAP = 4


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Retrocheevos")
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

        home_page = HomePage(self.app_context)

        # Home is the only root page; `_navigate_home` and logout use it.
        self._nav_pages = [home_page]
        # "ROM Location" became "Library": same two halves (the grid of
        # what's installed, and folder management plus scanning), its own
        # page again after a brief spell as an entry in the Lists dropdown.
        self._menu_pages = {
            "library": LibraryPage(self.app_context),
            "lists": ListsPage(self.app_context),
            "settings": SettingsPage(self.app_context),
        }

        home_page.navigate_requested.connect(self._on_menu_navigate)
        home_page.logout_requested.connect(self._on_logout)
        home_page.login_requested.connect(self._on_login)

        # Nothing was listening to this. `AppContext` emitted it on every
        # login/logout/switch and only the page that *caused* the change
        # refreshed itself — so signing in from Settings left Home, the
        # header and every other page holding the previous session's state
        # until the app was restarted. That was the "login only works after
        # reopening" bug.
        self.app_context.active_account_changed.connect(self._on_active_account_changed)

        # The header lives here, above the stack, so it shows on every page
        # rather than only on Home. It is built and owned by `HomePage`
        # (which already has the profile fetch, the avatar loader and the
        # user menu wired up); mounting it here means one instance instead of
        # a copy per page, each with its own duplicate of that plumbing.
        self._header = home_page.header_widget

        self._pages = QStackedWidget()
        for page in [*self._nav_pages, *self._menu_pages.values()]:
            self._pages.addWidget(page)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(
            WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN
        )
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addSpacing(HEADER_GAP)
        layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

        self._show_page(home_page)
        self._restore_window_state()

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
        """
        self._save_window_state()
        super().closeEvent(event)

    def _on_active_account_changed(self, _account) -> None:
        """Re-read whoever is now signed in, without navigating.

        Only the visible page is refreshed; the others refresh themselves on
        their way in (`_show_page`). Refreshing all of them here would run
        Home's several-second Recent Activity fetch every time someone opens
        Settings and switches account.
        """
        # Deliberately does **not** touch the window. Restoring the stored
        # state here meant logging out of a fullscreen session yanked the
        # window back to a smaller size mid-use, and logging in did it again.
        # The window is the user's current context, not account data: it is
        # applied once, at startup, and after that only ever follows what the
        # user does to it.
        self._nav_pages[0].refresh_header()
        current = self._pages.currentWidget()
        if current is not None:
            current.refresh()

    def _navigate_home(self) -> None:
        self._show_page(self._nav_pages[0])

    def _on_menu_navigate(self, key: str) -> None:
        # "home" is in the menu but not in `_menu_pages`: Home is the root
        # page, and duplicating it into that dict would give the app two
        # HomePage instances with two Recent Activity timers.
        if key == "home":
            self._navigate_home()
            return
        self._show_page(self._menu_pages[key])

    def _on_login(self, account_id: int) -> None:
        """Sign back in from the user menu. `refresh_active_account` fires
        `active_account_changed`, which repaints the header and the visible
        page — no restart, no trip to Settings."""
        session_service.switch_account(account_id)
        self.app_context.refresh_active_account()
        self._navigate_home()

    def _on_logout(self) -> None:
        session_service.logout()
        self.app_context.refresh_active_account()
        self._navigate_home()

    def _show_page(self, page: QWidget) -> None:
        self._pages.setCurrentWidget(page)
        page.refresh()
        # Home's own `refresh()` already covers the header; anywhere else it
        # would otherwise keep whatever numbers were last loaded.
        if page is not self._nav_pages[0]:
            self._nav_pages[0].refresh_header()
