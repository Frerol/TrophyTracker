"""Main application window and navigation (UI.md §2).

Two navigation paths land on the same `QStackedWidget`
(`Page.refresh()` always called after switching, regardless of path):
`_nav_list` (primary destinations — row index drives `_nav_pages`
directly) and `HomePage`'s user menu (Profile/Library/Lists/Settings,
`_menu_pages` keyed by the string each menu action emits). Dashboard was
retired once Home (`gui/pages/home_page.py`) fully absorbed its content
(Continue Playing, Recent Activity) — nothing else referenced it.

Both paths funnel through `_show_page`, which also maintains a browser-style
back/forward history (`_history`/`_history_index`, `_back_button`/
`_forward_button`) covering every page — nav and menu alike — so "back"
always returns to whatever was actually shown before, regardless of which
path got you there.
"""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.explorer_page import ExplorerPage
from retrocheevos.gui.pages.home_page import ICON_PATH, HomePage
from retrocheevos.gui.pages.leaderboards_page import LeaderboardsPage
from retrocheevos.gui.pages.library_page import LibraryPage
from retrocheevos.gui.pages.lists_page import ListsPage
from retrocheevos.gui.pages.profile_page import ProfilePage
from retrocheevos.gui.pages.settings_page import SettingsPage
from retrocheevos.services import session_service

NAV_ITEMS = ["Home", "Explorer", "Leaderboards"]

HISTORY_BUTTON_SIZE = 44
# 0, not negative: confirmed via `QWidget.geometry()` measurements that
# `QLayout.setSpacing()` does NOT support genuinely negative gaps — any
# negative value (tested -1 through -20) is silently discarded and
# replaced with the platform style's own default spacing (measured 6px
# here), identical regardless of how negative the argument was. `0` is the
# actual minimum — confirmed to produce a real, measured 0px gap between
# the two buttons (they touch exactly).
HISTORY_BUTTON_SPACING = 0
# Simple/rounded/discreet, matching Claude's own nav arrows — no border, no
# fill except a subtle hover/pressed highlight, muted gray text that dims
# further when disabled rather than a bordered button look.
HISTORY_BUTTON_STYLESHEET = """
QPushButton {
    border: none;
    background: transparent;
    border-radius: 8px;
    color: #9a9a9a;
    font-size: 24pt;
}
QPushButton:hover:enabled {
    background: rgba(255, 255, 255, 0.08);
    color: #e0e0e0;
}
QPushButton:pressed:enabled {
    background: rgba(255, 255, 255, 0.14);
}
QPushButton:disabled {
    color: #4a4a4a;
}
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RetroCheevos")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1200, 800)

        self.app_context = AppContext()

        # Every page ever shown, oldest first, plus a pointer into it —
        # classic browser back/forward. `_show_page(..., record_history=False)`
        # (used by `_on_back`/`_on_forward` themselves) moves the pointer
        # without appending, so going back and then navigating normally
        # again correctly discards the stale "forward" tail.
        self._history: list[QWidget] = []
        self._history_index: int = -1

        home_page = HomePage(self.app_context)
        explorer_page = ExplorerPage(self.app_context)
        leaderboards_page = LeaderboardsPage(self.app_context)

        # Order matches NAV_ITEMS — `_on_nav_row_changed` indexes into this
        # directly, same as the single QStackedWidget index this replaces.
        self._nav_pages = [home_page, explorer_page, leaderboards_page]
        self._menu_pages = {
            "profile": ProfilePage(self.app_context),
            "library": LibraryPage(self.app_context),
            "lists": ListsPage(self.app_context),
            "settings": SettingsPage(self.app_context),
        }

        home_page.navigate_requested.connect(self._on_menu_navigate)
        home_page.logout_requested.connect(self._on_logout)

        self._back_button = QPushButton("‹")
        self._forward_button = QPushButton("›")
        for button in (self._back_button, self._forward_button):
            button.setFixedSize(HISTORY_BUTTON_SIZE, HISTORY_BUTTON_SIZE)
            button.setStyleSheet(HISTORY_BUTTON_STYLESHEET)
            button.setEnabled(False)
        self._back_button.clicked.connect(self._on_back)
        self._forward_button.clicked.connect(self._on_forward)
        history_bar = QHBoxLayout()
        history_bar.setSpacing(HISTORY_BUTTON_SPACING)
        history_bar.addWidget(self._back_button)
        history_bar.addWidget(self._forward_button)
        history_bar.addStretch(1)

        self._nav_list = QListWidget()
        self._nav_list.addItems(NAV_ITEMS)
        self._nav_list.setMaximumWidth(160)
        # A previous pass connected `itemClicked` *alongside*
        # `currentRowChanged` here, to work around a "clicking Home after a
        # menu destination does nothing" report — but that report was never
        # actually reproduced (headless tests always showed
        # `currentRowChanged` firing correctly, including from row -1), and
        # `currentRowChanged` demonstrably does fire on any real row change
        # (going from -1 to 0 included — confirmed live). Keeping both
        # connected meant a single click on a *different* row fired BOTH
        # signals, each independently calling `_navigate_to_nav_page` — i.e.
        # `HomePage.refresh()` twice per click, back to back. That went
        # unnoticed while every worker it started was fast; once Recent
        # Activity's ~6.5s live API fetch (`_activity_worker`,
        # `services/activity_feed_service.py`) was added, the second
        # `refresh()` call reliably overwrote `self._activity_worker` while
        # the first one's `QThread` was still actually running — destroying
        # a live `QThread` is undefined behavior in Qt and was the real
        # cause of a native access-violation crash at startup (see
        # DevelopmentRoadmap.md). `currentRowChanged` alone is sufficient.
        self._nav_list.currentRowChanged.connect(self._on_nav_row_changed)

        nav_column = QVBoxLayout()
        nav_column.addLayout(history_bar)
        nav_column.addWidget(self._nav_list)

        self._pages = QStackedWidget()
        for page in [*self._nav_pages, *self._menu_pages.values()]:
            self._pages.addWidget(page)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addLayout(nav_column, stretch=0)
        layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

        # `setCurrentRow(0)` on a freshly-populated list goes from -1 -> 0,
        # a real change, so `currentRowChanged` fires and calls
        # `_navigate_to_nav_page(0)` on its own — no separate explicit
        # refresh() call needed here (see the crash note above for why an
        # extra one used to exist and why it's gone).
        self._nav_list.setCurrentRow(0)

    def _on_nav_row_changed(self, index: int) -> None:
        if index < 0:
            return
        self._navigate_to_nav_page(index)

    def _navigate_to_nav_page(self, index: int) -> None:
        self._show_page(self._nav_pages[index])

    def _on_menu_navigate(self, key: str) -> None:
        # Deselects the primary nav list (no row corresponds to a menu
        # destination) without letting that itself trigger a switch — the
        # `_show_page` call below is what actually does the navigating.
        self._nav_list.blockSignals(True)
        self._nav_list.setCurrentRow(-1)
        self._nav_list.blockSignals(False)
        self._show_page(self._menu_pages[key])

    def _on_logout(self) -> None:
        session_service.logout()
        self.app_context.refresh_active_account()
        # Same `blockSignals` dance as `_on_menu_navigate`: `setCurrentRow(0)`
        # only fires `currentRowChanged` (and thus a refresh) if the nav
        # list wasn't already on row 0 — blocking it and always calling
        # `_navigate_to_nav_page(0)` explicitly guarantees exactly one
        # refresh regardless of where navigation was before logout.
        self._nav_list.blockSignals(True)
        self._nav_list.setCurrentRow(0)
        self._nav_list.blockSignals(False)
        self._navigate_to_nav_page(0)

    def _show_page(self, page: QWidget, *, record_history: bool = True) -> None:
        self._pages.setCurrentWidget(page)
        page.refresh()
        if record_history:
            # Standard browser semantics: a fresh navigation discards
            # whatever "forward" entries existed past the current point.
            self._history = self._history[: self._history_index + 1]
            self._history.append(page)
            self._history_index = len(self._history) - 1
        self._update_history_buttons()

    def _sync_nav_selection(self, page: QWidget) -> None:
        # Reflects `page` in the sidebar's selection without re-triggering
        # `_on_nav_row_changed` (which would call `_show_page` again and
        # push a duplicate history entry) — same blocked-signal idiom as
        # `_on_menu_navigate`/`_on_logout`.
        self._nav_list.blockSignals(True)
        self._nav_list.setCurrentRow(
            self._nav_pages.index(page) if page in self._nav_pages else -1
        )
        self._nav_list.blockSignals(False)

    def _on_back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        page = self._history[self._history_index]
        self._sync_nav_selection(page)
        self._show_page(page, record_history=False)

    def _on_forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        page = self._history[self._history_index]
        self._sync_nav_selection(page)
        self._show_page(page, record_history=False)

    def _update_history_buttons(self) -> None:
        self._back_button.setEnabled(self._history_index > 0)
        self._forward_button.setEnabled(self._history_index < len(self._history) - 1)
