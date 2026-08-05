"""Home page (UI.md — unified home screen).

Phase 1 built the layout skeleton. Phase 2 wired in Continue Playing,
points, and Event Badges. Phase 3 added the user menu (Profile/Library/
Lists/Settings/Logout — `gui/main_window.py` handles the actual page
switching/logout, this page only emits what was picked) and Recent
Activity (absorbed from the now-retired `DashboardPage`). A follow-up pass
added the real profile photo (`API_GetUserProfile.php`'s `UserPic`,
confirmed live — same image base URL as game covers,
`library/game_images.py`) as the user menu button's icon, replacing the
generic-icon placeholder, and RetroRatio-weighted true points
(`TotalTruePoints`, shown alongside points the same way RA's own site
does) — both via `sync_service.sync_profile`, zero new sync entry point.

A later pass redesigned Recent Activity to match RA's own "Following"
page: avatar, last-activity timestamp, current game, an aggregate
achievements/playtime line, and a colored rich-presence status line, for
the account itself plus every followed user in one unified list — see
`services/activity_feed_service.py` for the live, non-persisted API reads
behind it (`ActivityEntryCard` per entry, no Message/Unfollow/Block
buttons). A loading label fills the section while that fetch (several
seconds, real API calls) is in flight.

A follow-up header pass: the user menu button is now a photo-only
`_HoverMenuButton` (no name) — a click is a shortcut straight to Profile,
hovering opens the same Profile/Library/Lists/Settings/Logout menu as
before. Points are stacked vertically (points/true points, blue/white, no
"pts"/parentheses) instead of one "X pts (Y true pts)" line, matching RA's
own site layout more closely. Back/forward history navigation
(browser-style, covering every page — nav and menu alike) lives in
`gui/main_window.py`, not here, since it needs to work from any page, not
just Home.

Phase 5: the center search bar is a launcher (`_search_launcher_button`) —
clicking it hides Continue Playing/Recent Activity and shows a second,
independent `ExplorerPage` instance (`self._explorer_page`) in their place,
unmodified from the standalone Explorer nav page. Deliberately two
separate `ExplorerPage` instances (not one shared/reparented widget) —
reparenting a `QTableView` between containers touches the same class of
geometry-change code implicated in Explorer's earlier native crash
(`gui/delegates/explorer_delegates.py`'s module docstring), so this phase
doesn't attempt it. No animation, either, for the same reason — instant
`setVisible()` toggling only. `HomePage.refresh()` always collapses back
to the default state; the embedded page's own `refresh()` only runs while
actually expanded (cache-only, cheap — see `ExplorerPage`'s own
docstring — so it's safe to re-run on every expand, not just the first).

Still-placeholder:
  - Phase 6/7: Games Beaten + Friends leaderboards — contingent on a
    research spike (RA API coverage unconfirmed; this project's own
    DevelopmentRoadmap.md already deferred Leaderboards to Version 1.2).
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.core.activity_feed import build_activity_feed
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.pages.explorer_page import ExplorerPage
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.models.activity_feed import ActivityEntry
from retrocheevos.services import (
    activity_feed_service,
    console_service,
    dashboard_service,
    image_service,
    library_service,
    profile_service,
)
from retrocheevos.widgets.activity_entry_card import ActivityEntryCard
from retrocheevos.widgets.game_card import GameCard

logger = logging.getLogger(__name__)

USER_MENU_DESTINATIONS = [
    ("profile", "Profile"),
    ("library", "Library"),
    ("lists", "Lists"),
    ("settings", "Settings"),
]

PROJECT_ROOT = Path(__file__).resolve().parents[4]
LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"
# `logo.png` is non-square (889x561, just the "RC" artwork) — fine for this
# page's own inline header (scaled by height, aspect ratio preserved), but
# forcing it into a square window/taskbar icon slot stretched it visibly.
# `icon.png` is the same artwork centered on a square transparent canvas —
# used for `MainWindow`/`QApplication.setWindowIcon` instead, never here.
ICON_PATH = PROJECT_ROOT / "assets" / "icon.png"
LOGO_HEIGHT = 32

SIDEBAR_MAX_WIDTH = 260
CONTINUE_PLAYING_GRID_COLUMNS = 4
CONTINUE_PLAYING_MIN_HEIGHT = 220
ACTIVITY_LOADING_TEXT = "Loading recent activity…"
ACTIVITY_ERROR_TEXT = "Couldn't load recent activity."
USER_AVATAR_SIZE = 48
POINTS_COLOR = "#4a90e2"
TRUE_POINTS_COLOR = "#f0f0f0"
POINTS_FONT_SIZE = 13
TRUE_POINTS_FONT_SIZE = 11
# 0, not negative: confirmed via `QWidget.geometry()` measurements (same
# finding as `HISTORY_BUTTON_SPACING` in `main_window.py`) that
# `QLayout.setSpacing()` silently discards any negative value and
# substitutes the platform style's own default spacing instead — measured
# identical (+6px) for every value from -1 to -20 tried. `0` is the real
# floor: measured a genuine 0px gap between the two labels.
POINTS_SPACING = 0
MENU_CLOSE_POLL_MS = 150


def _placeholder_group(title: str, phase_note: str) -> QGroupBox:
    group = QGroupBox(title)
    group_layout = QVBoxLayout(group)
    group_layout.addWidget(QLabel(phase_note))
    return group


HOVER_MENU_DELAY_MS = 120


class _HoverMenuButton(QPushButton):
    """A QPushButton where hover and click do different things — click
    still emits Qt's normal `clicked`, `hovered` is this class's own
    addition for the destinations menu (see `HomePage._show_user_menu`).

    `hovered` fires after a short delay, not immediately on `enterEvent`:
    the menu it opens used to be a blocking `QMenu.exec()` call, and the
    mouse always enters a widget before it can click it — firing `hovered`
    immediately meant every click's press/release landed inside that
    already-open menu instead of reaching the button, so a plain click
    could never fire `clicked` at all. Delaying it and cancelling on
    press/leave lets a normal quick click go through untouched, while a
    genuine hover-and-wait still opens the menu — 120ms is short enough to
    feel immediate for an intentional hover while still comfortably
    outlasting a real click's press-to-release time.
    """

    hovered = Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self.hovered.emit)

    def enterEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._hover_timer.start(HOVER_MENU_DELAY_MS)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._hover_timer.stop()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._hover_timer.stop()
        super().mousePressEvent(event)


class HomePage(Page):
    # `str` is the key from USER_MENU_DESTINATIONS — `gui/main_window.py`
    # owns the actual page instances/switching, this page only reports
    # what was picked (same "emit, don't reach into MainWindow" shape as
    # every other page's existing signals, e.g. GameCard.play_requested).
    navigate_requested = Signal(str)
    logout_requested = Signal()

    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._play_worker: Optional[ServiceWorker] = None
        self._photo_worker: Optional[ServiceWorker] = None
        self._activity_worker: Optional[ServiceWorker] = None
        self._user_menu: Optional[QMenu] = None
        self._activity_entries: list[ActivityEntry] = []

        app_name_label = QLabel("RetroCheevos")
        app_name_font = app_name_label.font()
        app_name_font.setBold(True)
        app_name_font.setPointSize(app_name_font.pointSize() + 4)
        app_name_label.setFont(app_name_font)

        # Logo + name side by side, matching RetroAchievements' own site
        # header — falls back to name-only if the asset is ever missing,
        # rather than crashing the page over a missing image file.
        logo_label = QLabel()
        logo_pixmap = QPixmap(str(LOGO_PATH))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(
                logo_pixmap.scaledToHeight(
                    LOGO_HEIGHT, Qt.TransformationMode.SmoothTransformation
                )
            )

        # Points stacked vertically, no "pts"/parentheses — matches RA's own
        # site (points in one color, RetroRatio-weighted true points below
        # in another) rather than the earlier single-line "X pts (Y true
        # pts)" text. Font set directly (not via stylesheet) so
        # `QFontMetrics` below reflects the real rendered size — a QLabel's
        # sizeHint() reserves a full line's leading above/below the glyphs,
        # which reads as "too much gap" even with zero layout spacing;
        # clamping each label to its font's actual ascent+descent removes it.
        self._points_label = QLabel()
        points_font = self._points_label.font()
        points_font.setBold(True)
        points_font.setPointSize(POINTS_FONT_SIZE)
        self._points_label.setFont(points_font)
        self._points_label.setStyleSheet(f"color: {POINTS_COLOR};")

        self._true_points_label = QLabel()
        true_points_font = self._true_points_label.font()
        true_points_font.setPointSize(TRUE_POINTS_FONT_SIZE)
        self._true_points_label.setFont(true_points_font)
        self._true_points_label.setStyleSheet(f"color: {TRUE_POINTS_COLOR};")

        for points_display_label in (self._points_label, self._true_points_label):
            points_display_label.setContentsMargins(0, 0, 0, 0)
            metrics = QFontMetrics(points_display_label.font())
            # Ascent only, no descent: these labels only ever hold digits
            # and commas, which don't extend below the baseline, so
            # reserving descent space was pure empty gap between the two
            # stacked numbers.
            points_display_label.setFixedHeight(metrics.ascent())

        points_column = QVBoxLayout()
        points_column.setContentsMargins(0, 0, 0, 0)
        points_column.setSpacing(POINTS_SPACING)
        # Without this, the two fixed-height labels were shorter than the
        # row's tallest sibling (the 60px avatar button next to them), and
        # `top_bar` (a QHBoxLayout) gave `points_column` that full row
        # height — `QVBoxLayout` then distributed the *unused* leftover
        # height as extra gap between the two labels rather than packing
        # them together, even at `setSpacing(0)`. Confirmed via
        # `QWidget.geometry()`: without `AlignTop` the measured gap was 9px
        # regardless of the spacing value; with it, 0px.
        points_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        points_column.addWidget(self._points_label, alignment=Qt.AlignmentFlag.AlignRight)
        points_column.addWidget(self._true_points_label, alignment=Qt.AlignmentFlag.AlignRight)

        # Photo only, no name — click is a shortcut straight to Profile,
        # hover opens the full destinations menu (`_show_user_menu`, still
        # Profile/Library/Lists/Settings/Logout). Icon is the real profile
        # photo once `refresh()`'s background load finishes
        # (`_on_photo_ready`) — the 👤 emoji is only the fallback for before
        # that first completes, or if there's no cached/synced photo yet.
        self._user_avatar_button = _HoverMenuButton("👤")
        self._user_avatar_button.setIconSize(QSize(USER_AVATAR_SIZE, USER_AVATAR_SIZE))
        self._user_avatar_button.setFixedSize(USER_AVATAR_SIZE + 12, USER_AVATAR_SIZE + 12)
        self._user_avatar_button.clicked.connect(lambda: self.navigate_requested.emit("profile"))
        self._user_avatar_button.hovered.connect(self._show_user_menu)

        top_bar = QHBoxLayout()
        top_bar.addWidget(logo_label)
        top_bar.addWidget(app_name_label)
        top_bar.addStretch(1)
        top_bar.addLayout(points_column)
        # `points_column` itself is `AlignTop` (packs its own two labels
        # tightly, see above) — separately, `top_bar` was stretching that
        # whole block to the row's full height (set by its taller sibling,
        # the 60px avatar button), so the compact 2-line block sat at the
        # *top* of the row while the avatar sat centered in it — visually
        # misaligned. This tells `top_bar` to center the block itself
        # instead of stretching it, aligning its midpoint with the
        # avatar's.
        top_bar.setAlignment(points_column, Qt.AlignmentFlag.AlignVCenter)
        top_bar.addWidget(self._user_avatar_button)

        # A launcher, not a real search field — Explorer's own search box
        # (part of `self._explorer_page`, unmodified) is what the user
        # actually types into once expanded. See module docstring for why
        # this stays two separate widgets instead of one shared field.
        self._search_launcher_button = QPushButton("🔍  Search games…")
        self._search_launcher_button.setStyleSheet(
            "text-align: left; padding: 6px 10px;"
        )
        self._search_launcher_button.clicked.connect(self._expand_explorer)

        self._back_to_home_button = QPushButton("‹ Back to Home")
        self._back_to_home_button.clicked.connect(self._collapse_explorer)
        self._back_to_home_button.setVisible(False)

        self._explorer_page = ExplorerPage(app_context)
        self._explorer_page.setVisible(False)

        self._continue_playing_container = QWidget()
        self._continue_playing_layout = QGridLayout(self._continue_playing_container)
        continue_playing_scroll = QScrollArea()
        continue_playing_scroll.setWidgetResizable(True)
        continue_playing_scroll.setMinimumHeight(CONTINUE_PLAYING_MIN_HEIGHT)
        continue_playing_scroll.setWidget(self._continue_playing_container)
        self._continue_playing_group = QGroupBox("Continue Playing")
        continue_playing_group_layout = QVBoxLayout(self._continue_playing_group)
        continue_playing_group_layout.addWidget(continue_playing_scroll)

        self._activity_feed_container = QWidget()
        self._activity_feed_layout = QVBoxLayout(self._activity_feed_container)
        activity_feed_scroll = QScrollArea()
        activity_feed_scroll.setWidgetResizable(True)
        activity_feed_scroll.setMinimumHeight(CONTINUE_PLAYING_MIN_HEIGHT)
        activity_feed_scroll.setWidget(self._activity_feed_container)
        self._recent_activity_group = QGroupBox("Recent Activity")
        recent_activity_group_layout = QVBoxLayout(self._recent_activity_group)
        recent_activity_group_layout.addWidget(activity_feed_scroll)

        center_column = QVBoxLayout()
        center_column.addWidget(self._search_launcher_button)
        center_column.addWidget(self._back_to_home_button)
        center_column.addWidget(self._explorer_page, stretch=1)
        center_column.addStretch(1)
        center_column.addWidget(self._continue_playing_group)
        center_column.addWidget(self._recent_activity_group)

        self._event_badges_list = QListWidget()
        event_badges_group = QGroupBox("Event Badges")
        event_badges_group_layout = QVBoxLayout(event_badges_group)
        event_badges_group_layout.addWidget(self._event_badges_list)

        sidebar_widget = QWidget()
        sidebar_widget.setMaximumWidth(SIDEBAR_MAX_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(_placeholder_group("Games Beaten", "Phase 6"))
        sidebar_layout.addWidget(_placeholder_group("Friends", "Phase 6"))
        sidebar_layout.addWidget(event_badges_group)
        sidebar_layout.addStretch(1)

        content_row = QHBoxLayout()
        content_row.addLayout(center_column, stretch=1)
        content_row.addWidget(sidebar_widget, stretch=0)

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addLayout(content_row, stretch=1)

    def refresh(self) -> None:
        # Always resets to collapsed — the embedded Explorer's own state
        # (filters, scroll position) isn't something Home tries to
        # remember across visits; matches "cache-only, must feel instant"
        # (UI.md §5) better than re-showing a possibly-stale expanded view.
        self._collapse_explorer()
        self._clear_continue_playing()
        self._event_badges_list.clear()
        self._clear_activity_feed()

        account = self.app_context.active_account
        if account is None:
            self._points_label.setText("No account selected.")
            self._true_points_label.setText("")
            self._user_avatar_button.setText("👤")
            self._user_avatar_button.setIcon(QIcon())
            return

        stats = profile_service.get_profile_stats(account.id)
        if stats is not None:
            self._points_label.setText(f"{stats.points:,}")
            self._true_points_label.setText(f"{stats.true_points:,}")
            # Skip starting a new fetch if the previous one is still
            # in flight (same "already pending, don't duplicate" idiom as
            # `gui/image_loader.py::ImageLoader.request`) — replacing a
            # still-running `QThread`'s only reference destroys it while
            # `run()` is executing, which is what caused a native crash
            # here once this fetch got slow (DevelopmentRoadmap.md).
            if self._photo_worker is None or not self._photo_worker.isRunning():
                self._photo_worker = ServiceWorker(
                    image_service.ensure_user_pic_cached, account.username, stats.user_pic_path
                )
                self._photo_worker.finished_ok.connect(self._on_photo_ready)
                self._photo_worker.start()
        else:
            self._points_label.setText("No synced stats yet.")
            self._true_points_label.setText("")

        console_names = {console.id: console.name for console in console_service.list_consoles()}
        for index, game in enumerate(dashboard_service.get_continue_playing_games(account.id)):
            card = GameCard(game, console_name=console_names.get(game.console_id))
            card.play_requested.connect(self._on_play)
            self._continue_playing_layout.addWidget(
                card, index // CONTINUE_PLAYING_GRID_COLUMNS, index % CONTINUE_PLAYING_GRID_COLUMNS
            )

        for badge in profile_service.get_badges(account.id):
            if badge.is_event:
                self._event_badges_list.addItem(badge.name)

        # This fetch is several real API calls deep (DevelopmentRoadmap.md)
        # and reliably takes a few seconds — an empty section with nothing
        # in it looks broken while it's in flight, so show a loading label
        # until the first entry streams in.
        self._activity_entries = []
        self._activity_feed_layout.addWidget(QLabel(ACTIVITY_LOADING_TEXT))

        # Same in-flight guard as `_photo_worker` above — this fetch does up
        # to `3 * (1 + FOLLOWED_USERS_LIMIT)` live API calls and reliably
        # takes several seconds, making it the most likely of this page's
        # workers to still be running if `refresh()` fires again quickly.
        if self._activity_worker is None or not self._activity_worker.isRunning():
            self._activity_worker = ServiceWorker(
                activity_feed_service.get_recent_activity_feed, account, stream_results=True
            )
            # `partial_result`: render each entry as it's fetched instead of
            # waiting for the whole ~several-second batch — feels much
            # faster even though the total fetch time is unchanged.
            # `finished_ok` still lands with the complete, correctly-sorted
            # list as the authoritative final state.
            self._activity_worker.partial_result.connect(self._on_activity_entry_ready)
            self._activity_worker.finished_ok.connect(self._on_activity_feed_ready)
            self._activity_worker.failed.connect(self._on_activity_feed_failed)
            self._activity_worker.start()

    def _clear_continue_playing(self) -> None:
        while self._continue_playing_layout.count():
            item = self._continue_playing_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_activity_feed(self) -> None:
        while self._activity_feed_layout.count():
            item = self._activity_feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _expand_explorer(self) -> None:
        self._search_launcher_button.setVisible(False)
        self._continue_playing_group.setVisible(False)
        self._recent_activity_group.setVisible(False)
        self._back_to_home_button.setVisible(True)
        self._explorer_page.setVisible(True)
        # Cache-only (ExplorerPage's own docstring: "must feel instant"),
        # so re-running this on every expand — not just the first — costs
        # nothing beyond a cheap DB re-query, and keeps results fresh if
        # e.g. a sync happened elsewhere since the last expand.
        self._explorer_page.refresh()

    def _collapse_explorer(self) -> None:
        self._explorer_page.setVisible(False)
        self._back_to_home_button.setVisible(False)
        self._search_launcher_button.setVisible(True)
        self._continue_playing_group.setVisible(True)
        self._recent_activity_group.setVisible(True)

    def _on_activity_entry_ready(self, entry: ActivityEntry) -> None:
        self._activity_entries.append(entry)
        self._render_activity_entries(build_activity_feed(self._activity_entries))

    def _on_activity_feed_ready(self, entries: list[ActivityEntry]) -> None:
        # Authoritative final state — already-sorted, from `finished_ok`.
        # Normally identical to what streaming in via `partial_result`
        # already built up, but this is what actually wins if the two ever
        # disagree (e.g. zero entries: no `partial_result` ever fired, so
        # this is the only thing that clears the loading label).
        self._activity_entries = entries
        self._render_activity_entries(entries)

    def _render_activity_entries(self, entries: list[ActivityEntry]) -> None:
        self._clear_activity_feed()
        for entry in entries:
            self._activity_feed_layout.addWidget(ActivityEntryCard(entry))

    def _on_activity_feed_failed(self, message: str) -> None:
        # Without this, a failure (e.g. the API's own rate limit — see
        # `activity_feed_service.py`) left the loading label showing
        # forever with no feedback, since nothing ever replaced it.
        logger.warning("Recent activity fetch failed: %s", message)
        if not self._activity_entries:
            self._clear_activity_feed()
            self._activity_feed_layout.addWidget(QLabel(ACTIVITY_ERROR_TEXT))

    def _on_play(self, game_id: int) -> None:
        self._play_worker = ServiceWorker(library_service.launch_game, game_id)
        self._play_worker.failed.connect(self._on_play_failed)
        self._play_worker.start()

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)

    def _on_photo_ready(self, cached_path) -> None:
        # `ensure_user_pic_cached` never raises (see image_service.py) —
        # `None` means "no photo yet" or "download failed," not an error;
        # the 👤 text fallback set in refresh() is already in place either way.
        if not cached_path:
            return
        pixmap = QPixmap(str(cached_path))
        if pixmap.isNull():
            return
        self._user_avatar_button.setIcon(QIcon(pixmap))
        self._user_avatar_button.setText("")

    def _show_user_menu(self) -> None:
        if self._user_menu is not None:
            return  # already open (e.g. re-entering the button while it's showing)

        menu = QMenu(self._user_avatar_button)
        for key, label in USER_MENU_DESTINATIONS:
            action = menu.addAction(label)
            action.triggered.connect(self._make_navigate_handler(key))
        menu.addSeparator()
        menu.addAction("Logout", self.logout_requested.emit)
        self._user_menu = menu

        # `QMenu` has no built-in "close when the cursor leaves" — only
        # click-away/Escape/action-triggered. Polling the cursor against
        # the button's and the menu's own rect and closing it once it's in
        # neither is the standard way to get that hover-dropdown feel.
        # `popup()` (non-blocking), not `exec()` (blocking): this poll
        # timer needs the event loop free to keep firing while the menu is
        # open.
        close_poll_timer = QTimer(menu)
        close_poll_timer.setInterval(MENU_CLOSE_POLL_MS)
        close_poll_timer.timeout.connect(lambda: self._close_menu_if_cursor_left(menu))
        menu.aboutToHide.connect(close_poll_timer.stop)
        menu.aboutToHide.connect(self._on_user_menu_closed)
        close_poll_timer.start()

        menu.popup(self._user_avatar_button.mapToGlobal(self._user_avatar_button.rect().bottomLeft()))

    def _close_menu_if_cursor_left(self, menu: QMenu) -> None:
        pos = QCursor.pos()
        over_button = self._user_avatar_button.rect().contains(
            self._user_avatar_button.mapFromGlobal(pos)
        )
        over_menu = menu.geometry().contains(pos)
        if not (over_button or over_menu):
            menu.close()

    def _on_user_menu_closed(self) -> None:
        self._user_menu = None

    def _make_navigate_handler(self, key: str):
        return lambda: self.navigate_requested.emit(key)
