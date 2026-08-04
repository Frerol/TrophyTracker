"""Main application window and navigation (UI.md §2)."""

from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.dashboard_page import DashboardPage
from retrocheevos.gui.pages.explorer_page import ExplorerPage
from retrocheevos.gui.pages.leaderboards_page import LeaderboardsPage
from retrocheevos.gui.pages.library_page import LibraryPage
from retrocheevos.gui.pages.lists_page import ListsPage
from retrocheevos.gui.pages.profile_page import ProfilePage
from retrocheevos.gui.pages.settings_page import SettingsPage

NAV_ITEMS = ["Dashboard", "Explorer", "Library", "Profile", "Leaderboards", "Lists", "Settings"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RetroCheevos")
        self.resize(1200, 800)

        self.app_context = AppContext()

        self._nav_list = QListWidget()
        self._nav_list.addItems(NAV_ITEMS)
        self._nav_list.setMaximumWidth(160)
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)

        self._pages = QStackedWidget()
        self._pages.addWidget(DashboardPage(self.app_context))
        self._pages.addWidget(ExplorerPage(self.app_context))
        self._pages.addWidget(LibraryPage(self.app_context))
        self._pages.addWidget(ProfilePage(self.app_context))
        self._pages.addWidget(LeaderboardsPage(self.app_context))
        self._pages.addWidget(ListsPage(self.app_context))
        self._pages.addWidget(SettingsPage(self.app_context))

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self._nav_list, stretch=0)
        layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

        self._nav_list.setCurrentRow(0)
        self._pages.currentWidget().refresh()

    def _on_nav_changed(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        self._pages.currentWidget().refresh()
