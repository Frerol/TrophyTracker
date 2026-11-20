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

Phase 5: the center search bar reveals a second, independent `ExplorerPage`
instance (`self._explorer_page`) in place of Continue Playing/Recent
Activity, unmodified from the standalone Explorer nav page. Deliberately two
separate `ExplorerPage` instances (not one shared/reparented widget) —
reparenting a `QTableView` between containers touches the same class of
geometry-change code implicated in Explorer's earlier native crash
(`gui/delegates/explorer_delegates.py`'s module docstring), so this phase
doesn't attempt it. No animation, either, for the same reason — instant
`setVisible()` toggling only. `HomePage.refresh()` always collapses back
to the default state; the embedded page's own `refresh()` only runs while
actually expanded (cache-only, cheap — see `ExplorerPage`'s own
docstring — so it's safe to re-run on every expand, not just the first).

A later pass (Bloco 5) replaced the click-to-expand launcher button with a
real, always-visible `QLineEdit` (`self._search_input`) — typing into it is
what expands the embedded Explorer now (`_on_search_text_changed`), via a
new `ExplorerPage.set_search_text()` that forwards the text into that page's
own field and triggers results immediately, rather than waiting for Enter
(the standalone Explorer nav page's own field still requires Enter — this
change only affects how Home's field drives it). Clearing the field, or
"Back to Home", collapses back to Continue Playing/Recent Activity.
"""

from dataclasses import replace
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from retrocheevos.models.account import Account

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.core.activity_feed import build_activity_feed
from retrocheevos.gui import styles
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.pages.base_page import Page
from retrocheevos.gui.pages.explorer_page import ExplorerPage
from retrocheevos.gui.workers import ServiceWorker
from retrocheevos.library.rom_title import derive_title_from_filename
from retrocheevos.models.activity_feed import ActivityEntry, ActivityFeedResult
from retrocheevos.models.library import InstalledRom
from retrocheevos.services import (
    activity_feed_service,
    console_service,
    dashboard_service,
    events_service,
    image_service,
    library_service,
    notification_service,
    preferences_service,
    profile_service,
    session_service,
    sync_service,
)
from retrocheevos.widgets.activity_entry_card import ActivityEntryCard
from retrocheevos.widgets.continue_playing_game_row import ContinuePlayingGameRow
from retrocheevos.widgets.cover_size_slider import CoverSizeSlider
from retrocheevos.widgets.event_row import EventRow
from retrocheevos.widgets.unmatched_rom_card import UnmatchedRomCard
from retrocheevos.widgets.now_playing_panel import NowPlayingPanel

logger = logging.getLogger(__name__)

USER_MENU_DESTINATIONS = [
    # "home" isn't in `MainWindow._menu_pages` — it's the root page, handled
    # as a special case in `_on_menu_navigate`. Listed first because it's
    # where "get me back" belongs, and because clicking the photo (rather
    # than hovering it) now goes straight here.
    ("home", "Home"),
    ("library", "Library"),
    ("lists", "Lists"),
    ("settings", "Settings"),
]

def _assets_dir() -> Path:
    """Where `assets/` lives, from source and from a frozen build.

    PyInstaller unpacks bundled data into a temporary directory it points
    `sys._MEIPASS` at; `__file__` inside the bundle resolves somewhere else
    entirely, so the source-relative path finds nothing and the logo and
    window icon silently fail to load in the .exe. Checked at call time, not
    import time, because `_MEIPASS` only exists in a frozen process.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "assets"
    return Path(__file__).resolve().parents[4] / "assets"


PROJECT_ROOT = Path(__file__).resolve().parents[4]
LOGO_PATH = _assets_dir() / "logo.png"
# The shared emblem is used in the header and as the desktop icon.
ICON_PATH = _assets_dir() / "icon.png"
LOGO_HEIGHT = 60

# Keep room for the game grid while leaving event titles readable.
SIDEBAR_MIN_WIDTH = 280
SIDEBAR_MAX_WIDTH = 340
COVER_SIZE_BASELINE = 75
# Frame border + card margins + grid spacing around the cover, so the column
# count reflects the space a card really takes rather than the art alone.
CONTINUE_PLAYING_CARD_PADDING = 24
# Vertical scrollbar (14px, `gui/styles.py`) plus the scroll area's 1px
# border each side. It was 34 — padding piled on padding, which cost a whole
# column at some sizes and left a wide dead strip on the right, the same way
# it did in the Library.
CONTINUE_PLAYING_VIEWPORT_CHROME = 16
MIN_CONTINUE_PLAYING_COLUMNS = 2
MAX_CONTINUE_PLAYING_ENTRIES = 50
CONTINUE_PLAYING_MIN_HEIGHT = 160
REFRESH_BUTTON_TEXT = "Refresh"
LOGOUT_ACTION_TEXT = "Logout"
LOGIN_ACTION_TEXT = "Login"
ADD_ACCOUNT_ACTION_TEXT = "Add an account…"
ACTIVITY_LOADING_TEXT = "Loading recent activity…"
ACTIVITY_ERROR_TEXT = "Couldn't load recent activity."
# What one refresh actually costs, counted from `activity_feed_service`:
# one call for the follow list, then two per user (summary + game progress)
# across self plus up to `FOLLOWED_USERS_LIMIT` (30) followed accounts —
# about 63 requests, paced 0.3s apart, so roughly 19 seconds of API traffic.
#
# At the old 30s interval that was ~126 requests a minute, sustained for as
# long as Home stayed open: heavier than the hash backfill (~115/min), and
# unlike the backfill it never finishes. It also spent 19 of every 30
# seconds mid-fetch, so any slowdown had refreshes treading on each other.
# The visible symptom was Recent Activity failing outright during a catalog
# sync — the two were competing for the same burst limiter — but the feed
# was over-fetching on its own long before any sync started.
#
# Three minutes is chosen against what the data actually is: rich presence
# and "last game played" don't move on a 30-second scale, and a refresh
# takes 19s regardless, so the extra latency is imperceptible while the
# request rate drops roughly sixfold.
ACTIVITY_REFRESH_INTERVAL_MS = 180_000
# On failure the interval doubles up to this ceiling, resetting on the next
# success (see `_on_activity_feed_failed`). A failed fetch is nearly always
# the API's burst limiter, and retrying at full cadence into a limiter is
# what turns one rate-limited call into a stream of them — during a hash
# backfill the old code failed every 30s for the entire hour.
ACTIVITY_BACKOFF_CEILING_MS = 1_500_000  # 25 minutes
EVENTS_MIN_HEIGHT = 320
NEW_EVENTS_BANNER_COLOR = styles.LINK
MAX_BANNER_EVENT_NAMES = 3
# Opened externally rather than rebuilt in-app: RA exposes no API for this
# ranking, and scraping it isn't something this project does.
BEATEN_GAMES_LEADERBOARD_URL = "https://retroachievements.org/ranking/beaten-games"
USER_AVATAR_SIZE = 36
# The header band's height is **pinned**, not derived from whatever is
# tallest inside it. It used to come from the avatar button, which meant
# resizing the photo silently resized the whole top of every page — a change
# nobody asked for each time. Now the photo can change freely and the band
# stays put; this constant is the only thing that moves it.
HEADER_HEIGHT = 96
# Gap between the points block and the photo.
POINTS_AVATAR_GAP = 8
# How far the points+photo group sits below the top of the band.
RIGHT_GROUP_DROP = 16
# Frame around the avatar image inside its button. Shared with the points
# block, which is pinned to the same total height so the two centre together.
AVATAR_FRAME_PAD = 8
# Matches the page's own layout margin so header and content share one left
# edge, and keeps the avatar off the right-hand window edge.
HEADER_SIDE_MARGIN = 24
# Profile totals use the mint accent and neutral heading color.
POINTS_COLOR = styles.POINTS_BLUE
TRUE_POINTS_COLOR = styles.HEADING
POINTS_FONT_SIZE = 18
TRUE_POINTS_FONT_SIZE = 12
APP_NAME_FONT_SIZE = 26
# Gap between the emblem and the wordmark.
LOGO_TEXT_GAP = 14
# Twice the height the stats line takes below `top_bar` — a top margin of
# this size shifts the lockup's centre down by half of it, landing it on the
# centre of the full header band.
LOGO_BAND_OFFSET = 18
STATS_FONT_DELTA = 2
# 0, not negative: confirmed via `QWidget.geometry()` measurements (same
# finding as `HISTORY_BUTTON_SPACING` in `main_window.py`) that
# `QLayout.setSpacing()` silently discards any negative value and
# substitutes the platform style's own default spacing instead — measured
# identical (+6px) for every value from -1 to -20 tried. `0` is the real
# floor: measured a genuine 0px gap between the two labels.
POINTS_SPACING = 0
MENU_CLOSE_POLL_MS = 150


def _continue_playing_sort_key(entry: tuple) -> tuple:
    """Ordering for Continue Playing: unfinished games first (most recently
    played, then most progress), finished ones last, alphabetical to break
    ties.

    A single ascending key rather than several `sort()` passes — the "most
    recent/most progress first" parts are expressed by negating the numeric
    values, since `reverse=True` would also flip the alphabetical tiebreak.
    `None` sorts last within each group (never played / no progress yet)
    instead of dropping out.
    """
    last_played, percent_complete, title, _item = entry
    is_finished = percent_complete is not None and percent_complete >= 100
    return (
        1 if is_finished else 0,
        0 if last_played is not None else 1,
        -last_played.timestamp() if last_played is not None else 0.0,
        0 if percent_complete is not None else 1,
        -(percent_complete or 0.0),
        title.lower(),
    )


# Stable keys used with AppContext's WorkerRegistry so shutdown can cancel
# every background job this page owns, and so "is a job already running?"
# checks don't rely on a dangling QThread reference.
HOME_WORKER_ACTIVITY = ("home", "activity")
HOME_WORKER_PHOTO = ("home", "photo")
HOME_WORKER_PROFILE_SYNC = ("home", "profile-sync")
HOME_WORKER_PLAY = ("home", "play")


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
    # every other page's existing signals, e.g. ContinuePlayingGameRow.play_requested).
    navigate_requested = Signal(str)
    logout_requested = Signal()
    login_requested = Signal(int)  # account_id

    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
        self._user_menu: Optional[QMenu] = None
        self._activity_entries: list[ActivityEntry] = []
        self._activity_cards: dict[str, tuple[ActivityEntry, ActivityEntryCard]] = {}
        # See `_refresh_activity_feed`: only an initial load renders entries
        # as they stream in; a background refresh swaps the finished list in
        # one go, so the section never blanks out mid-update.
        self._stream_activity_entries = True
        # Last completed feed, kept across navigations (`_activity_entries`
        # is reset at the start of every fetch, so it can't serve this).
        self._activity_cache: list[ActivityEntry] = []
        # Which account the cached feed belongs to (R01). Without this, an
        # account switch could paint the previous account's feed while the
        # new one loads — the cache survives navigation by design, but it
        # must not survive a change of user.
        self._activity_cache_account_id: Optional[int] = None
        # Bumped on every account change. Workers capture it before starting
        # and ignore their result if it has moved by the time they finish, so
        # a slow fetch for account A can never land on account B's Home (R01).
        self._account_generation = 0
        # Per-request generation/account for the activity fetch. Separate from
        # `_account_generation` because a manual refresh while the same account
        # is signed in should also invalidate the older in-flight request.
        self._activity_request_generation = 0
        self._activity_request_account_id: Optional[int] = None
        # Account generation of the activity fetch currently in flight.
        self._activity_request_account_gen: Optional[int] = None
        self._activity_refresh_pending = False
        self._photo_worker_key = HOME_WORKER_PHOTO
        # One shared loader for every ContinuePlayingGameRow built by
        # refresh() — registered with AppContext so shutdown can wait for it.
        self._image_loader = app_context.create_image_loader()

        # R01: invalidate anything account-bound the moment the session
        # changes, before MainWindow refreshes the visible page.
        self.app_context.active_account_changed.connect(self._on_active_account_changed)

        # Only ticks while Home is the visible page (started/stopped in
        # showEvent/hideEvent below) — keeps Recent Activity current without
        # spending RA API calls while the user is elsewhere in the app.
        self._activity_refresh_timer = QTimer(self)
        self._activity_refresh_timer.setInterval(ACTIVITY_REFRESH_INTERVAL_MS)
        self._activity_refresh_timer.timeout.connect(
            lambda: self._refresh_activity_feed(show_loading=False)
        )
        # Current backoff, in milliseconds. Kept separate from the timer's own
        # interval so `showEvent` can restart at the base cadence without
        # having to know what the last failure had stretched it to.
        self._activity_retry_interval_ms = ACTIVITY_REFRESH_INTERVAL_MS
        # `time.monotonic()` of the last fetch *attempt*, or None if none yet.
        self._activity_last_attempt: Optional[float] = None

        logo_label = QLabel()
        logo_label.setObjectName("brandMark")
        logo_pixmap = QPixmap(str(LOGO_PATH))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(
                LOGO_HEIGHT, LOGO_HEIGHT, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        logo_label.setFixedSize(LOGO_HEIGHT, LOGO_HEIGHT)
        app_name_label = QLabel("TrophyTracker")
        app_name_label.setObjectName("brandName")
        tagline = QLabel("Your games. Your achievements.")
        tagline.setObjectName("brandTagline")
        wordmark = QVBoxLayout()
        wordmark.setSpacing(2)
        wordmark.addWidget(app_name_label)
        wordmark.addWidget(tagline)
        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo_row.addWidget(logo_label)
        logo_row.addLayout(wordmark)

        self._points_label = QLabel("—")
        self._true_points_label = QLabel("—")
        self._points_label.setStyleSheet(f"color: {styles.LINK}; font-size: 18pt; font-weight: 600;")
        self._true_points_label.setStyleSheet(f"color: {styles.HEADING}; font-size: 18pt; font-weight: 600;")
        right_row = QHBoxLayout()
        right_row.setSpacing(24)
        for caption, value in (("POINTS", self._points_label), ("RETRO POINTS", self._true_points_label)):
            column = QVBoxLayout()
            column.setSpacing(2)
            label = QLabel(caption)
            label.setObjectName("eyebrow")
            column.addWidget(label)
            column.addWidget(value)
            right_row.addLayout(column)
        self._user_avatar_button = _HoverMenuButton("●")
        self._user_avatar_button.setObjectName("accountButton")
        self._user_avatar_button.setAccessibleName("Account menu")
        self._user_avatar_button.setToolTip("Accounts and session")
        self._user_avatar_button.setIconSize(QSize(USER_AVATAR_SIZE, USER_AVATAR_SIZE))
        self._user_avatar_button.setFixedSize(USER_AVATAR_SIZE + AVATAR_FRAME_PAD, USER_AVATAR_SIZE + AVATAR_FRAME_PAD)
        self._user_avatar_button.clicked.connect(self._show_user_menu)
        self._user_avatar_button.hovered.connect(self._show_user_menu)
        right_row.addWidget(self._user_avatar_button)
        top_bar = QHBoxLayout()
        top_bar.addLayout(logo_row)
        top_bar.addStretch(1)
        top_bar.addLayout(right_row)

        # Always-visible real search field — typing (not a click-to-expand
        # step) is what reveals the embedded Explorer's results below, via
        # `_on_search_text_changed`. Forwards the typed text into
        # `self._explorer_page`'s own field (`set_search_text`) rather than
        # being a second, independent query — still one shared field's worth
        # of typed text, just displayed as two widgets so the Explorer page
        # itself (used standalone from the nav sidebar too) isn't touched.
        self._search_input = QLineEdit()
        self._search_input.setObjectName("globalSearch")
        self._search_input.setPlaceholderText("Search your next game…")
        self._search_input.textChanged.connect(self._on_search_text_changed)

        self._back_to_home_button = QPushButton("‹ Back to Home")
        self._back_to_home_button.clicked.connect(self._on_back_to_home_clicked)
        self._back_to_home_button.setVisible(False)

        # The page itself stays visible at all times — only its results area
        # is toggled (`set_results_visible`), so the filter pills sit under
        # the search box from the start and can be used to open the results
        # without typing anything.
        self._explorer_page = ExplorerPage(app_context)
        self._explorer_page.set_results_visible(False)
        self._explorer_page.filters_changed.connect(self._on_explorer_filters_changed)
        self._explorer_page.sync_finished.connect(self._on_sync_finished)

        self._continue_playing_container = QWidget()
        self._continue_playing_layout = QGridLayout(self._continue_playing_container)
        # Top-aligned: the *group* stretches to fill the column (that's the
        # point), but its cards must keep their natural height. Without this
        # a single card inflates to the full panel — a 40px cover in a 230px
        # frame — because the grid spreads its one row over all the space.
        self._continue_playing_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._continue_playing_scroll = QScrollArea()
        # Vertical only. A horizontal bar here means the column count was
        # wrong — the grid is supposed to fit the width by construction
        # (`_continue_playing_columns` measures the viewport) — so turning it
        # off makes that a visible layout bug rather than something the user
        # has to scroll past. Nothing gets cut: the column count is derived
        # from `viewport().width()`, which already excludes the vertical
        # bar's own width.
        self._continue_playing_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        continue_playing_scroll = self._continue_playing_scroll
        # Tracked so `resizeEvent` only rebuilds when the count really moves.
        self._last_continue_playing_columns = 0
        continue_playing_scroll.setWidgetResizable(True)
        continue_playing_scroll.setMinimumHeight(CONTINUE_PLAYING_MIN_HEIGHT)
        continue_playing_scroll.setWidget(self._continue_playing_container)
        self._cover_slider = CoverSizeSlider(
            initial_size=preferences_service.get_int(
                preferences_service.KEY_CONTINUE_PLAYING_COVER_SIZE, COVER_SIZE_BASELINE
            ),
            label="Cover size",
            min_size=75,
            max_size=125,
        )
        self._cover_slider.size_changed.connect(self._on_cover_size_changed)

        self._continue_playing_group = QGroupBox("Continue Playing")
        continue_playing_group_layout = QVBoxLayout(self._continue_playing_group)
        # Re-reads what's installed without leaving Home. Deliberately only
        # refreshes this section: a full `refresh()` would also restart the
        # Recent Activity fetch, several seconds of live API calls that have
        # nothing to do with "did my ROM folder change".
        continue_playing_refresh = QPushButton(REFRESH_BUTTON_TEXT)
        continue_playing_refresh.setToolTip(
            "Re-read what's installed and drop anything gone"
        )
        continue_playing_refresh.clicked.connect(self._on_refresh_continue_playing)

        continue_playing_slider_row = QHBoxLayout()
        continue_playing_slider_row.addWidget(self._cover_slider)
        continue_playing_slider_row.addWidget(continue_playing_refresh)
        continue_playing_slider_row.addStretch(1)
        continue_playing_group_layout.addLayout(continue_playing_slider_row)
        continue_playing_group_layout.addWidget(continue_playing_scroll)

        self._activity_feed_container = QWidget()
        self._activity_feed_layout = QVBoxLayout(self._activity_feed_container)
        # Same reason as Continue Playing's grid above.
        self._activity_feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        activity_feed_scroll = QScrollArea()
        activity_feed_scroll.setWidgetResizable(True)
        activity_feed_scroll.setMinimumHeight(CONTINUE_PLAYING_MIN_HEIGHT)
        activity_feed_scroll.setWidget(self._activity_feed_container)
        self._recent_activity_group = QGroupBox("Recent Activity")
        recent_activity_group_layout = QVBoxLayout(self._recent_activity_group)
        recent_activity_group_layout.addWidget(activity_feed_scroll)

        # Continue Playing and Recent Activity take the leftover vertical
        # space themselves, one share each. There used to be an empty spacer
        # widget above them holding `stretch=1`, which is exactly what left a
        # dead gap between the search field and these two sections.
        #
        # No spacer is needed to keep the explorer working either: a *hidden*
        # widget contributes zero stretch, and `_expand_explorer` hides both
        # groups, so when the results table is open it is the only thing left
        # competing for the space. Collapsed, the explorer must still set its
        # own stretch back to 0 explicitly — it is never hidden (its filter
        # bar stays on screen), so it can't rely on that rule itself.
        self._center_column = QVBoxLayout()
        self._now_playing = NowPlayingPanel()
        self._now_playing.progress_updated.connect(self._refresh_continue_playing)
        self.app_context.active_account_changed.connect(self._now_playing.set_account)
        self._now_playing.set_account(self.app_context.active_account)
        self._center_column.addWidget(self._search_input)
        self._center_column.addWidget(self._back_to_home_button)
        self._center_column.addWidget(self._explorer_page)
        self._center_column.addWidget(self._now_playing)
        self._center_column.addWidget(self._continue_playing_group, stretch=1)
        self._center_column.addWidget(self._recent_activity_group, stretch=1)
        center_column = self._center_column

        # Real events from the Events console, replacing a list that only
        # showed the names of *awards* the account had already earned — that
        # could never show an event you hadn't started, which is exactly the
        # set worth looking at. See `services/events_service.py`.
        self._new_events_banner = QLabel()
        self._new_events_banner.setWordWrap(True)
        self._new_events_banner.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_events_banner.setStyleSheet(
            f"color: {NEW_EVENTS_BANNER_COLOR}; font-weight: bold;"
        )
        self._new_events_banner.setToolTip("Click to dismiss")
        self._new_events_banner.setVisible(False)
        self._new_events_banner.mouseReleaseEvent = self._on_new_events_banner_clicked

        self._events_container = QWidget()
        self._events_layout = QVBoxLayout(self._events_container)
        self._events_layout.setContentsMargins(0, 0, 0, 0)
        events_scroll = QScrollArea()
        events_scroll.setWidgetResizable(True)
        events_scroll.setMinimumHeight(EVENTS_MIN_HEIGHT)
        events_scroll.setWidget(self._events_container)
        # A styled label rather than the QGroupBox title it used to be, so it
        # matches the "Beaten Games Leaderboard" button directly above it —
        # same box, same gold, centred. It is not clickable and not a
        # disabled button (see `styles.SECTION_HEADER_STYLESHEET`).
        events_header = QLabel("Events")
        events_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        events_header.setStyleSheet(styles.SECTION_HEADER_STYLESHEET)

        events_group = QWidget()
        events_group_layout = QVBoxLayout(events_group)
        events_group_layout.setContentsMargins(0, 0, 0, 0)
        events_group_layout.addWidget(events_header)
        events_group_layout.addWidget(self._new_events_banner)
        events_group_layout.addWidget(events_scroll)

        # The ranking page has no API behind it, so this is a link out rather
        # than something rebuilt in-app — same `QDesktopServices` one-liner
        # as `EventRow` and the game cards' "Open on RetroAchievements".
        leaderboard_button = QPushButton("Beaten Games Leaderboard")
        leaderboard_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(BEATEN_GAMES_LEADERBOARD_URL))
        )

        sidebar_widget = QWidget()
        # Minimum, not just maximum. The sidebar sits at `stretch=0`, so it
        # only ever gets its content's preferred width — raising the cap
        # alone did nothing (the event rows don't ask for more), and all the
        # extra space went to the centre column instead. The floor is what
        # actually widens it; the cap stops it eating the grid.
        sidebar_widget.setMinimumWidth(SIDEBAR_MIN_WIDTH)
        sidebar_widget.setMaximumWidth(SIDEBAR_MAX_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(leaderboard_button)
        sidebar_layout.addWidget(events_group, stretch=1)

        content_row = QHBoxLayout()
        # The live panel adds useful detail without imposing a taller minimum
        # window than a laptop screen. Scroll the column when space is tight.
        center_widget = QWidget()
        center_widget.setLayout(center_column)
        center_scroll = QScrollArea()
        center_scroll.setWidgetResizable(True)
        center_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        center_scroll.setWidget(center_widget)
        content_row.addWidget(center_scroll, stretch=1)
        content_row.addWidget(sidebar_widget, stretch=0)

        # Beaten/Mastered/Completion %, absorbed from the since-removed
        # Profile page — same source data (`profile_service.get_profile_stats`,
        # already fetched below for the points labels), sitting under
        # photo/name/points.
        self._stats_row_label = QLabel()
        self._stats_row_label.setStyleSheet(f"color: {styles.TEXT_DIM};")
        stats_font = self._stats_row_label.font()
        stats_font.setPointSize(stats_font.pointSize() + STATS_FONT_DELTA)
        self._stats_row_label.setFont(stats_font)
        stats_row = QHBoxLayout()
        self._displayed_account_label = QLabel()
        account = self.app_context.active_account
        self._displayed_account_label.setText(
            f"Account: {account.username}" if account else "No account selected"
        )
        stats_row.addWidget(self._displayed_account_label)
        stats_row.addStretch(1)
        stats_row.addWidget(self._stats_row_label)

        # The header (logo, name, points, stats, avatar menu) is packaged as
        # a widget rather than added to this page's layout, so `MainWindow`
        # can mount it *above the page stack* — one instance, visible on
        # every page, instead of four copies each needing their own signal
        # wiring and their own profile fetch. It still belongs to this page:
        # the labels are updated by `refresh()`/`_on_photo_ready` here, and
        # `refresh_header()` exists for MainWindow to freshen it when
        # navigating somewhere that isn't Home.
        self.header_widget = QWidget()
        self.header_widget.setObjectName("brandHeader")
        header_layout = QVBoxLayout(self.header_widget)
        # Side margins matching the page below, so the logo starts on the
        # same vertical line as the search field and the avatar isn't jammed
        # against the window edge. The header sits in `MainWindow`, outside
        # the page's own layout, so it doesn't inherit those margins.
        header_layout.setContentsMargins(
            HEADER_SIDE_MARGIN, 0, HEADER_SIDE_MARGIN, 0
        )
        # No gap between the logo row and the stats line under it — they read
        # as one band, and the default layout spacing was most of the band's
        # spare height.
        header_layout.setSpacing(0)
        # `stretch=1` so `top_bar` owns the band's spare height — otherwise
        # it is only as tall as its contents and "centre the logo" would
        # centre it in that smaller row, leaving it visibly high in the band.
        header_layout.addLayout(top_bar, stretch=1)
        header_layout.addLayout(stats_row)
        # Fixed, so the band no longer resizes when the avatar or the fonts
        # inside it change — see `HEADER_HEIGHT`.
        self.header_widget.setFixedHeight(HEADER_HEIGHT)

        layout = QVBoxLayout(self)
        layout.addLayout(content_row, stretch=1)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self._activity_refresh_timer.start()
        # Fetch straight away rather than waiting out a full interval —
        # coming back to Home after a while should show current data, not
        # whatever was on screen when you left. `refresh()` covers the
        # navigation path, but not e.g. un-minimising the window.
        #
        # Gated on the current interval, because this is the one path that
        # can bypass the backoff entirely: every arrival on Home is 63 API
        # requests, and bouncing between Home and Library a few times while
        # the limiter is already angry would fire all of them each way. The
        # cached feed is painted regardless, so the gate costs nothing
        # visible.
        if self._activity_refresh_is_due():
            self._refresh_activity_feed(show_loading=False)

    def _activity_refresh_is_due(self) -> bool:
        if self._activity_last_attempt is None:
            return True
        elapsed_ms = (time.monotonic() - self._activity_last_attempt) * 1000
        return elapsed_ms >= self._activity_retry_interval_ms

    def hideEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().hideEvent(event)
        self._activity_refresh_timer.stop()

    def _on_active_account_changed(self, account) -> None:
        # R01: cancel anything account-bound before it can land on the wrong
        # user's screen, and drop the cached feed if the user changed.
        self._account_generation += 1
        self._displayed_account_label.setText(
            f"Account: {account.username}" if account else "No account selected"
        )
        self.app_context.workers.cancel_key(HOME_WORKER_ACTIVITY)
        self.app_context.workers.cancel_key(self._photo_worker_key)
        self._photo_worker_key = (HOME_WORKER_PHOTO, self._account_generation)
        self._activity_refresh_pending = False
        self._user_avatar_button.setIcon(QIcon())
        self._user_avatar_button.setText("●")
        self._user_avatar_button.setToolTip(
            f"Displayed account: {account.username}" if account else "Choose an account"
        )
        self.app_context.workers.cancel_key(HOME_WORKER_PROFILE_SYNC)
        new_id = account.id if account is not None else None
        if self._activity_cache_account_id != new_id:
            self._activity_cache = []
            self._activity_entries = []
            self._clear_activity_feed()
            self._activity_cache_account_id = new_id
            self._activity_last_attempt = None
            self._activity_retry_interval_ms = ACTIVITY_REFRESH_INTERVAL_MS
            self._activity_refresh_timer.setInterval(ACTIVITY_REFRESH_INTERVAL_MS)

    def refresh_header(self) -> None:
        """Update just the shared header — points, stats, avatar.

        `MainWindow` calls this when navigating to a page that isn't Home, so
        the header on Library/Lists/Settings shows current numbers. Split out
        of `refresh()` deliberately: that one also kicks off the Recent
        Activity fetch, which is several seconds of live API calls and has no
        business running because someone opened Settings.
        """
        account = self.app_context.active_account
        if account is None:
            self._points_label.setText("—")
            self._true_points_label.setText("—")
            self._stats_row_label.setText("")
            self._user_avatar_button.setText("●")
            self._user_avatar_button.setIcon(QIcon())
            return

        stats = profile_service.get_profile_stats(account.id)
        if stats is None:
            self._points_label.setText("—")
            self._true_points_label.setText("—")
            self._stats_row_label.setText("")
            return

        self._points_label.setText(f"{stats.points:,}")
        self._true_points_label.setText(f"{stats.true_points:,}")
        self._stats_row_label.setText(
            f"Beaten: {stats.games_beaten}  |  Mastered: {stats.games_mastered}  |  "
            f"Completion: {stats.completion_percentage:.1f}%"
        )

    def refresh(self) -> None:
        self._now_playing.set_account(self.app_context.active_account)
        # Always resets to collapsed — the embedded Explorer's own state
        # (filters, scroll position) isn't something Home tries to
        # remember across visits; matches "cache-only, must feel instant"
        # (UI.md §5) better than re-showing a possibly-stale expanded view.
        self._search_input.blockSignals(True)
        self._search_input.clear()
        self._search_input.blockSignals(False)
        self._collapse_explorer()
        # The filter pills are on screen even while results are hidden, so
        # the Console pill needs its list now — `_expand_explorer`'s own
        # `refresh()` would populate it too, but only after the user has
        # already opened the pill and found it empty.
        self._explorer_page.load_consoles()
        self._clear_continue_playing()
        self._clear_events()
        # Recent Activity is deliberately *not* cleared here. It's the only
        # section backed by several seconds of live API calls, and wiping it
        # on every navigation back to Home meant staring at "Loading…" each
        # time for data that was already correct. `_refresh_activity_feed`
        # below decides whether to show that placeholder.

        account = self.app_context.active_account
        if account is None:
            self._points_label.setText("—")
            self._true_points_label.setText("—")
            self._stats_row_label.setText("")
            self._user_avatar_button.setText("●")
            self._user_avatar_button.setIcon(QIcon())
            # Dropped on logout/account switch, or the next account would
            # briefly see the previous one's feed painted from cache.
            self._activity_cache = []
            self._activity_entries = []
            self._activity_cache_account_id = None
            self._clear_activity_feed()
            return

        stats = profile_service.get_profile_stats(account.id)
        if stats is not None:
            self._points_label.setText(f"{stats.points:,}")
            self._true_points_label.setText(f"{stats.true_points:,}")
            self._stats_row_label.setText(
                f"Beaten: {stats.games_beaten}  |  Mastered: {stats.games_mastered}  |  "
                f"Completion: {stats.completion_percentage:.1f}%"
            )
            # Skip starting a new fetch if the previous one is still
            # in flight (same "already pending, don't duplicate" idiom as
            # `gui/image_loader.py::ImageLoader.request`) — replacing a
            # still-running `QThread`'s only reference destroys it while
            # `run()` is executing, which is what caused a native crash
            # here once this fetch got slow (DevelopmentRoadmap.md).
            if not self.app_context.workers.has_key(self._photo_worker_key):
                gen = self._account_generation
                account_id = account.id
                photo_worker = ServiceWorker(
                    image_service.ensure_user_pic_cached, account.username, stats.user_pic_path
                )
                photo_worker.finished_ok.connect(
                    lambda path: self._on_photo_ready_guarded(path, gen, account_id)
                )
                self.app_context.workers.start(photo_worker, key=self._photo_worker_key)
        else:
            self._points_label.setText("—")
            self._true_points_label.setText("—")
            self._stats_row_label.setText("")

        # Opportunistic, not periodic: only checked here, on activation/
        # revisit of Home, never on a timer. Cheap no-op if `profile_stats`
        # is still fresh (`sync_service.PROFILE_SYNC_STALE_AFTER`) — self-heals
        # stale points (e.g. `true_points` stuck at its migration-v8 backfill
        # default of 0) without hammering the API on every restart/switch.
        # Same in-flight guard as `_photo_worker`/`_activity_worker` above.
        self._start_profile_sync(account)

        # Continue Playing lists installed ROMs too, so it needs the same
        # sweep the Library does — otherwise a game deleted from disk keeps
        # showing here even after the Library has dropped it.
        library_service.purge_missing_roms()
        self._refresh_continue_playing()
        self._refresh_events()
        # Re-show what we already have straight away, then refresh behind it.
        # Only a cold start (nothing cached, or the account changed) gets the
        # "Loading…" placeholder.
        if self._activity_cache:
            self._render_activity_entries(self._activity_cache)
        self._refresh_activity_feed(show_loading=not self._activity_cache)

    def _clear_events(self) -> None:
        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refresh_events(self) -> None:
        """Rebuilds the Events list and the "new events" banner above it."""
        self._clear_events()

        account = self.app_context.active_account
        if account is None:
            self._new_events_banner.setVisible(False)
            return

        unread = notification_service.list_unread_events(account.id)
        unread_ids = {n.game_id for n in unread}
        if unread:
            names = ", ".join(n.message for n in unread[:MAX_BANNER_EVENT_NAMES])
            more = len(unread) - MAX_BANNER_EVENT_NAMES
            suffix = f" and {more} more" if more > 0 else ""
            self._new_events_banner.setText(f"{len(unread)} new event(s): {names}{suffix}")
            self._new_events_banner.setVisible(True)
        else:
            self._new_events_banner.setVisible(False)

        for entry in events_service.list_events_with_progress(account.id):
            self._events_layout.addWidget(
                EventRow(entry, self._image_loader, is_new=entry.game.id in unread_ids)
            )
        self._events_layout.addStretch(1)

    def _on_new_events_banner_clicked(self, _event) -> None:
        account = self.app_context.active_account
        if account is None:
            return
        notification_service.mark_events_read(account.id)
        self._refresh_events()

    def _on_sync_finished(self, new_event_ids: list) -> None:
        """The embedded Explorer's "Sync Everything" just finished — turn any
        newly-appeared events into notifications and redraw the section.
        """
        account = self.app_context.active_account
        if account is None:
            return
        if new_event_ids:
            known = {
                entry.game.id: entry.game.title
                for entry in events_service.list_events_with_progress(account.id)
            }
            notification_service.record_new_events(
                account.id,
                [(game_id, known.get(game_id, "New event")) for game_id in new_event_ids],
            )
        self._refresh_events()

    def _refresh_continue_playing(self) -> None:
        # Same reason as the Library's: the slider read its value at
        # construction, possibly with nobody signed in, so the account's
        # stored size has to be re-applied here.
        self._cover_slider.set_value_silently(
            preferences_service.get_int(
                preferences_service.KEY_CONTINUE_PLAYING_COVER_SIZE, COVER_SIZE_BASELINE
            )
        )
        """Rebuilds just the Continue Playing grid.

        Split out of `refresh()` so launching a game can re-sort the grid
        (the launch stamps `last_played_at`, which drives the ordering)
        without also re-triggering the several-second Recent Activity fetch
        and the profile sync that a full `refresh()` would.
        """
        self._clear_continue_playing()

        account = self.app_context.active_account
        if account is None:
            return

        console_names = {console.id: console.name for console in console_service.list_consoles()}

        # One combined sequence — matched games and unmatched-ROM fallbacks
        # interleaved, not shown as two separate blocks. Sorted by: last
        # played (most recent first), then games with tracked progress ahead
        # of untouched ones, then title. Never-played entries sort last
        # rather than disappearing (`datetime.min` is always the smallest).
        entries: list[tuple[Optional[datetime], Optional[float], str, object]] = [
            (entry.last_played_at, entry.percent_complete, entry.game.title, entry.game)
            for entry in dashboard_service.get_continue_playing_games(account.id)
        ]
        entries += [
            (rom.last_played_at, None, derive_title_from_filename(rom.file_path), rom)
            for rom in dashboard_service.get_unmatched_continue_playing_roms(account.id)
        ]
        entries.sort(key=_continue_playing_sort_key)
        # Capped *after* sorting, so the 50 kept are the 50 most recently
        # played rather than an arbitrary 50. Continue Playing is a shortcut
        # to what you're in the middle of; past a certain point it stops
        # being that and the Library is the full list.
        entries = entries[:MAX_CONTINUE_PLAYING_ENTRIES]

        cover_size = self._cover_slider.value()
        # Build every card first, then work out the column count from how
        # wide they actually came out. Placing them as they're built means
        # committing to a column count before knowing the width.
        # One lookup for the whole grid, not one per card.
        cover_guesses = library_service.guess_games_for_unmatched_roms()
        cards: list[QWidget] = []
        for _last_played, percent_complete, _title, item in entries:
            if isinstance(item, InstalledRom):
                card = UnmatchedRomCard(
                    item,
                    console_name=console_names.get(item.console_id),
                    cover_game=cover_guesses.get(item.id),
                    image_loader=self._image_loader,
                    cover_size=cover_size,
                    # Continue Playing's cards all carry a bar; an unmatched
                    # ROM's sits at zero so the row stays uniform.
                    show_progress=True,
                )
                card.play_requested.connect(self._on_play_unmatched_rom)
            else:
                card = ContinuePlayingGameRow(
                    item,
                    self._image_loader,
                    console_name=console_names.get(item.console_id),
                    percent_complete=percent_complete,
                    cover_size=cover_size,
                )
                card.play_requested.connect(self._on_play)
            cards.append(card)

        widest = max((card.sizeHint().width() for card in cards), default=cover_size)
        columns = self._columns_for_card_width(widest)
        for index, card in enumerate(cards):
            self._continue_playing_layout.addWidget(
                card,
                index // columns,
                index % columns,
                alignment=Qt.AlignmentFlag.AlignHCenter,
            )
        # Leftover width shared between the columns rather than piling up on
        # the right — the cards are fixed-width, so without this the
        # remainder sat as one dead block at the end of every row.
        for column in range(columns):
            self._continue_playing_layout.setColumnStretch(column, 1)

    def _on_cover_size_changed(self, size: int) -> None:
        preferences_service.set_int(
            preferences_service.KEY_CONTINUE_PLAYING_COVER_SIZE, size
        )
        self._refresh_continue_playing()

    def _on_refresh_continue_playing(self) -> None:
        """Sweep for files deleted outside the app, then redraw the section."""
        library_service.purge_missing_roms()
        self._refresh_continue_playing()

    def _columns_for_card_width(self, card_width: int) -> int:
        """Columns that fit, from the card's **measured** width.

        The previous version estimated it as `cover_size + a padding
        constant`. That constant can't be right for every size — the card's
        margins scale with the cover, the frame has borders, and the grid
        adds its own spacing — so at some sizes the estimate came out under
        the truth and the last column was clipped. Measuring one real card
        removes the guess.
        """
        available = self._continue_playing_scroll.viewport().width()
        if available <= 1:
            available = self.width() - SIDEBAR_MIN_WIDTH
        spacing = max(0, self._continue_playing_layout.horizontalSpacing())
        usable = max(0, available - CONTINUE_PLAYING_VIEWPORT_CHROME)
        return max(
            MIN_CONTINUE_PLAYING_COLUMNS, (usable + spacing) // (card_width + spacing)
        )

    def _continue_playing_columns(self, cover_size: int) -> int:
        """How many cards fit across right now, from the real viewport width.

        This used to scale a fixed 6-column baseline against the cover size
        (`6 * 40 // cover`), which meant 40px covers always got exactly 6
        columns — the cards then stretched to fill the row and you got six
        mostly-empty boxes instead of the many small ones the slider was
        asking for. The count has to come from the space available, not from
        a ratio.
        """
        available = self._continue_playing_scroll.viewport().width()
        if available <= 1:
            # Before the first layout the viewport reports a placeholder.
            available = self.width() - SIDEBAR_MIN_WIDTH
        usable = max(0, available - CONTINUE_PLAYING_VIEWPORT_CHROME)
        return max(
            MIN_CONTINUE_PLAYING_COLUMNS,
            usable // (cover_size + CONTINUE_PLAYING_CARD_PADDING),
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Reflow Continue Playing when the column count changes.

        Guarded on the count, not fired per pixel: a resize is continuous and
        rebuilding the grid that often would stutter.
        """
        super().resizeEvent(event)
        columns = self._continue_playing_columns(self._cover_slider.value())
        if columns != self._last_continue_playing_columns:
            self._last_continue_playing_columns = columns
            self._refresh_continue_playing()

    def _refresh_activity_feed(self, *, show_loading: bool) -> None:
        """Kicks off the Recent Activity fetch — called by `refresh()`
        (full page load, `show_loading=True`) and by `_activity_refresh_timer`
        (silent periodic background refresh, `show_loading=False`) alike.

        `show_loading=False` skips the "Loading…" flash: current entries
        stay on screen until the first new one streams in and
        `_render_activity_entries` swaps them in, instead of the whole
        section blanking out on every tick.
        """
        account = self.app_context.active_account
        if account is None or self.app_context._shutting_down:
            return
        if self.app_context.workers.has_key(HOME_WORKER_ACTIVITY):
            # Only queue a retry when the in-flight fetch belongs to an
            # earlier account generation (cancelled, results discarded). A
            # fetch already running for this account will deliver its own
            # results; re-running it right after would double the API calls.
            if self._activity_request_account_gen != self._account_generation:
                self._activity_refresh_pending = True
            return
        self._activity_refresh_pending = False
        self._activity_last_attempt = time.monotonic()

        self._activity_entries = []
        # Streaming is only ever shown on a load that starts from nothing.
        #
        # On the silent 30s refresh it caused a visible glitch: the old feed
        # stayed up (by design), then the *first* new entry to arrive
        # triggered a re-render that cleared the section and left a single
        # card, which then grew back one card at a time. From the outside
        # that reads as the content vanishing and reappearing every half
        # minute. Silent refreshes now render once, when the complete sorted
        # list lands in `_on_activity_feed_ready`.
        self._stream_activity_entries = show_loading
        if show_loading:
            self._clear_activity_feed()
            self._activity_feed_layout.addWidget(QLabel(ACTIVITY_LOADING_TEXT))

        gen = self._account_generation
        self._activity_request_account_gen = gen
        request_gen = self._activity_request_generation + 1
        self._activity_request_generation = request_gen
        account_id = account.id
        self._activity_request_account_id = account_id

        activity_worker = ServiceWorker(
            activity_feed_service.get_recent_activity_feed,
            account,
            stream_results=True,
            cancellable=True,
        )

        def handle_partial(entry):
            if gen != self._account_generation or request_gen != self._activity_request_generation:
                return
            if self.app_context.active_account is None or self.app_context.active_account.id != account_id:
                return
            self._on_activity_entry_ready(entry)

        def handle_ready(entries):
            if gen != self._account_generation or request_gen != self._activity_request_generation:
                return
            if self.app_context.active_account is None or self.app_context.active_account.id != account_id:
                return
            self._activity_cache_account_id = account_id
            self._on_activity_feed_ready(entries)

        def handle_failed(message):
            if gen != self._account_generation or request_gen != self._activity_request_generation:
                return
            if self.app_context.active_account is None or self.app_context.active_account.id != account_id:
                return
            self._on_activity_feed_failed(message)

        activity_worker.partial_result.connect(handle_partial)
        activity_worker.finished_ok.connect(handle_ready)
        activity_worker.failed.connect(handle_failed)
        activity_worker.cancelled.connect(lambda: None)
        self.app_context.workers.start(activity_worker, key=HOME_WORKER_ACTIVITY)
        # Connected after registry.start so its ownership entry is removed first.
        activity_worker.finished.connect(self._retry_pending_activity)

    def _retry_pending_activity(self) -> None:
        if self._activity_refresh_pending:
            self._activity_refresh_pending = False
            if self.app_context.active_account is not None and not self.app_context._shutting_down:
                QTimer.singleShot(0, lambda: self._refresh_activity_feed(
                    show_loading=not self._activity_cache
                ))

    def _start_profile_sync(self, account: Account) -> Optional[ServiceWorker]:
        from retrocheevos.services.job_coordinator import (
            try_acquire, release, JOB_SYNC_PROFILE,
        )

        if (
            self.app_context._shutting_down
            or self.app_context.workers.has_key(HOME_WORKER_PROFILE_SYNC)
        ):
            return None
        token = try_acquire(JOB_SYNC_PROFILE)
        if token is None:
            return None
        try:
            gen, account_id = self._account_generation, account.id
            client = session_service.build_api_client(account)
            worker = ServiceWorker(
                sync_service.sync_profile_if_needed, client, account, cancellable=True
            )
            worker.finished_ok.connect(
                lambda synced: self._on_profile_sync_done_guarded(synced, gen, account_id)
            )
            worker.failed.connect(
                lambda message: self._on_profile_sync_failed_guarded(message, gen, account_id)
            )
            worker.finished.connect(lambda: release(token))
            return self.app_context.workers.start(worker, key=HOME_WORKER_PROFILE_SYNC)
        except Exception:
            release(token)
            raise

    def _clear_continue_playing(self) -> None:
        # Column stretches outlive `takeAt`, so going from a wide layout to a
        # narrower one would leave phantom stretched columns on the right.
        for column in range(self._continue_playing_layout.columnCount()):
            self._continue_playing_layout.setColumnStretch(column, 0)
        while self._continue_playing_layout.count():
            item = self._continue_playing_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_activity_feed(self) -> None:
        self._activity_cards.clear()
        while self._activity_feed_layout.count():
            item = self._activity_feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _results_expanded(self) -> bool:
        return self._continue_playing_group.isHidden()

    def _expand_explorer(self) -> None:
        self._now_playing.hide()
        # Neither `self._search_input` nor the embedded page's filter bar is
        # ever hidden — they're always on screen; only the results area
        # beneath them toggles.
        self._continue_playing_group.setVisible(False)
        self._recent_activity_group.setVisible(False)
        self._back_to_home_button.setVisible(True)
        self._explorer_page.set_results_visible(True)
        self._center_column.setStretchFactor(self._explorer_page, 1)
        # Cache-only (ExplorerPage's own docstring: "must feel instant"),
        # so re-running this on every expand — not just the first — costs
        # nothing beyond a cheap DB re-query, and keeps results fresh if
        # e.g. a sync happened elsewhere since the last expand.
        self._explorer_page.refresh()

    def _collapse_explorer(self) -> None:
        self._now_playing.show()
        self._explorer_page.set_results_visible(False)
        self._center_column.setStretchFactor(self._explorer_page, 0)
        self._back_to_home_button.setVisible(False)
        self._continue_playing_group.setVisible(True)
        self._recent_activity_group.setVisible(True)

    def _on_explorer_filters_changed(self) -> None:
        # Touching a pill is as much a "show me results" gesture as typing
        # is — but only ever opens the results, never closes them (clearing
        # a filter shouldn't yank the user back to the dashboard).
        if not self._results_expanded():
            self._expand_explorer()

    def _on_search_text_changed(self, text: str) -> None:
        # `_results_expanded()`, not `self._explorer_page.isVisible()` — the
        # page is always visible now (its filter bar is), so its visibility
        # no longer tells us whether results are showing.
        if text.strip():
            if not self._results_expanded():
                self._expand_explorer()
            self._explorer_page.set_search_text(text)
        elif self._results_expanded():
            self._collapse_explorer()

    def _on_back_to_home_clicked(self) -> None:
        # Blocked, not just cleared: `clear()` alone would re-enter
        # `_on_search_text_changed` (harmlessly — it would just collapse
        # again) but there's no reason to run that handler a second time
        # for a state change already being driven from here.
        self._search_input.blockSignals(True)
        self._search_input.clear()
        self._search_input.blockSignals(False)
        self._collapse_explorer()

    def _on_activity_entry_ready(self, entry: ActivityEntry) -> None:
        self._activity_entries.append(entry)
        if not self._stream_activity_entries:
            return
        self._render_activity_entries(build_activity_feed(self._activity_entries))

    def _on_activity_feed_ready(self, result: ActivityFeedResult) -> None:
        entries = {entry.username.casefold(): entry for entry in result.entries}
        failed = {username.casefold() for username in result.failed_usernames}
        for entry in self._activity_cache:
            key = entry.username.casefold()
            if key not in entries and (key in failed or result.following_unavailable):
                entries[key] = entry
            elif key in entries and entries[key].progress_unavailable:
                fresh = entries[key]
                if (fresh.game_title, fresh.game_console) == (entry.game_title, entry.game_console):
                    entries[key] = replace(
                        fresh, achievements_unlocked=entry.achievements_unlocked,
                        achievements_total=entry.achievements_total,
                        playtime_seconds=entry.playtime_seconds,
                    )
        merged = build_activity_feed(list(entries.values()))
        self._activity_entries = merged
        self._activity_cache = merged
        if result.partial:
            self._back_off_activity_refresh()
            self._recent_activity_group.setTitle("Recent Activity — partially updated")
        else:
            self._reset_activity_refresh_interval()
            self._recent_activity_group.setTitle("Recent Activity")
        self._render_activity_entries(merged)
        if not merged and result.partial:
            self._activity_feed_layout.addWidget(QLabel(ACTIVITY_ERROR_TEXT))

    def _render_activity_entries(self, entries: list[ActivityEntry]) -> None:
        # Repaints suppressed across the teardown/rebuild: without it Qt
        # paints the empty container between the clear and the re-add, which
        # is a one-frame flash on every render.
        self._activity_feed_container.setUpdatesEnabled(False)
        try:
            self._render_activity_entries_now(entries)
        finally:
            self._activity_feed_container.setUpdatesEnabled(True)

    def _render_activity_entries_now(self, entries: list[ActivityEntry]) -> None:
        desired = {entry.username.casefold(): entry for entry in entries}
        # Keep unchanged cards alive, including when streaming reorders them.
        for key, (previous, card) in list(self._activity_cards.items()):
            if key not in desired or desired[key] != previous:
                self._activity_feed_layout.removeWidget(card)
                card.deleteLater()
                del self._activity_cards[key]
        # Remove loading/error labels without tearing down cards.
        for index in range(self._activity_feed_layout.count() - 1, -1, -1):
            widget = self._activity_feed_layout.itemAt(index).widget()
            if isinstance(widget, QLabel):
                self._activity_feed_layout.takeAt(index)
                widget.deleteLater()
        for index, entry in enumerate(entries):
            key = entry.username.casefold()
            if key not in self._activity_cards:
                self._activity_cards[key] = (entry, ActivityEntryCard(entry))
            self._activity_feed_layout.insertWidget(index, self._activity_cards[key][1])

    def _on_activity_feed_failed(self, message: str) -> None:
        logger.warning("Recent activity fetch failed: %s", message)
        self._back_off_activity_refresh()
        self._recent_activity_group.setTitle("Recent Activity — could not refresh")
        # A silent refresh starts with an empty streamed list. Preserve the
        # last good feed rather than replacing it with an error label.
        entries = self._activity_cache or self._activity_entries
        if entries:
            self._activity_entries = list(entries)
            self._render_activity_entries(entries)
        else:
            self._clear_activity_feed()
            self._activity_feed_layout.addWidget(QLabel(ACTIVITY_ERROR_TEXT))

    def _back_off_activity_refresh(self) -> None:
        """Double the refresh interval, up to the ceiling.

        A failure here is almost always RA's burst limiter, and the thing
        that makes that worse is retrying into it at full cadence: 63
        requests, fail, wait 30s, 63 requests, fail. Through an hour-long
        hash backfill the old code did exactly that, start to finish.

        Deliberately blind to *why* it failed. Special-casing the rate-limit
        error would leave every other failure — no network, RA down, an
        expired key — hammering just as hard, and backing off is the right
        response to all of them.
        """
        self._activity_retry_interval_ms = min(
            self._activity_retry_interval_ms * 2, ACTIVITY_BACKOFF_CEILING_MS
        )
        self._activity_refresh_timer.setInterval(self._activity_retry_interval_ms)
        logger.info(
            "Recent activity refresh backed off to %ds",
            self._activity_retry_interval_ms // 1000,
        )

    def _reset_activity_refresh_interval(self) -> None:
        """Back to the base cadence after a success, so one bad patch of
        network doesn't leave the feed on a 25-minute timer for the rest of
        the session.
        """
        if self._activity_retry_interval_ms == ACTIVITY_REFRESH_INTERVAL_MS:
            return
        self._activity_retry_interval_ms = ACTIVITY_REFRESH_INTERVAL_MS
        self._activity_refresh_timer.setInterval(ACTIVITY_REFRESH_INTERVAL_MS)
        logger.info("Recent activity refresh back to %ds", ACTIVITY_REFRESH_INTERVAL_MS // 1000)

    def _on_play(self, game_id: int) -> None:
        play_worker = ServiceWorker(library_service.launch_game, game_id)
        play_worker.finished_ok.connect(self._on_play_started)
        play_worker.failed.connect(self._on_play_failed)
        self.app_context.workers.start(play_worker, key=HOME_WORKER_PLAY)

    def _on_play_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Couldn't launch game", message)

    def _on_play_started(self, _result: object) -> None:
        self._now_playing.refresh_progress(force=True)
        # A successful launch stamps `installed_roms.last_played_at`, which
        # is what Continue Playing sorts by — without this the game the user
        # just started stays wherever it was until they navigate away and
        # back. Only this section is rebuilt (see `_refresh_continue_playing`).
        self._refresh_continue_playing()

    def _on_play_unmatched_rom(self, installed_rom_id: int) -> None:
        play_worker = ServiceWorker(library_service.launch_installed_rom, installed_rom_id)
        play_worker.finished_ok.connect(self._on_play_started)
        play_worker.failed.connect(self._on_play_failed)
        self.app_context.workers.start(play_worker, key=HOME_WORKER_PLAY)

    def _on_profile_sync_done_guarded(self, synced: bool, generation: int, account_id: int) -> None:
        if generation != self._account_generation:
            return
        account = self.app_context.active_account
        if account is None or account.id != account_id:
            return
        self._on_profile_sync_done(synced)

    def _on_profile_sync_failed_guarded(self, message: str, generation: int, account_id: int) -> None:
        if generation != self._account_generation:
            return
        account = self.app_context.active_account
        if account is None or account.id != account_id:
            return
        self._on_profile_sync_failed(message)

    def _on_profile_sync_done(self, synced: bool) -> None:
        # `synced` is False for the common case (cache still fresh) — nothing
        # to redraw. `True` means new stats landed, so re-run `refresh()` to
        # show them; that call's own staleness check then finds a just-updated
        # `last_synced_at` and returns False immediately, so this can't loop.
        if synced:
            self.refresh()

    def _on_profile_sync_failed(self, message: str) -> None:
        # Never surfaced to the user (e.g. `QMessageBox`) — this is a
        # best-effort background refresh, not a user-initiated action; the
        # manual "Sync Profile" button on the Profile page is what reports
        # failures. Just log for diagnosis.
        logger.info("Opportunistic profile sync skipped/failed: %s", message)

    def _on_photo_ready_guarded(self, cached_path, generation: int, account_id: int) -> None:
        if generation != self._account_generation:
            return
        account = self.app_context.active_account
        if account is None or account.id != account_id:
            return
        self._on_photo_ready(cached_path)

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
        self._add_session_actions(menu)
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

    def _add_session_actions(self, menu: QMenu) -> None:
        """"Logout" when signed in, "Login" when not.

        Offering "Logout" with nobody signed in was a dead entry, and the way
        back in was buried in Settings — so the menu that got you out had no
        matching way back. Three cases:

        - signed in            -> Logout
        - signed out, 1 account -> "Login as <name>", straight in
        - signed out, several   -> one entry per account, so the choice is
          made here rather than by going to Settings to switch first
        """
        active = self.app_context.active_account
        if active is not None:
            account_menu = QMenu(f"Displayed account: {active.username}", menu)
            menu.addMenu(account_menu)
            for account in session_service.list_accounts():
                action = account_menu.addAction(
                    account.username, self._make_login_handler(account.id)
                )
                action.setCheckable(True)
                action.setChecked(account.id == active.id)
            menu.addAction(LOGOUT_ACTION_TEXT, self.logout_requested.emit)
            return

        accounts = session_service.list_accounts()
        if not accounts:
            # Nothing to log into yet — send them where accounts are added
            # instead of showing a Login that can't do anything.
            menu.addAction(ADD_ACCOUNT_ACTION_TEXT, self._make_navigate_handler("settings"))
            return

        if len(accounts) == 1:
            account = accounts[0]
            menu.addAction(
                f"{LOGIN_ACTION_TEXT} as {account.username}",
                self._make_login_handler(account.id),
            )
            return

        for account in accounts:
            menu.addAction(
                f"{LOGIN_ACTION_TEXT} as {account.username}",
                self._make_login_handler(account.id),
            )

    def _make_login_handler(self, account_id: int):
        return lambda: self.login_requested.emit(account_id)

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
