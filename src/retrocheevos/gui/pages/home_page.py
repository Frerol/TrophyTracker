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

R18 moved the brand, the displayed account and its menu into the
application sidebar (`gui/sidebar.py`).

R19 rebuilt the page after the reviewed Home board: a header with sync
freshness and Sync now (a forced profile sync under the job slot), the
catalog search with "Explore catalog"/"Your lists" chips, four metric cards,
Continue Playing (`widgets/continue_playing_row.py`, combined "X/Y
achievements" counts per D8 and guarded Play) beside Recent Activity at
about 2:1, then Now Playing and the awards summary. The two-column rows stack
below `STACK_BELOW_WIDTH`. The cover size slider and the Events column are
gone; events and awards live in the Awards view (D7). The paragraphs below
describe earlier passes; the Explorer's filters and sync bar now only show
while the catalog is open.

Phase 5: the center search bar reveals a second, independent `ExplorerPage`
instance (`self._explorer_page`) in place of Continue Playing/Recent
Activity, unmodified from the standalone Explorer nav page. Deliberately two
separate `ExplorerPage` instances (not one shared/reparented widget) —
reparenting a `QTableView` between containers touches the same class of
geometry-change code implicated in Explorer's earlier native crash
(`gui/delegates/explorer_delegates.py`'s module docstring), so this phase
doesn't attempt it. No animation, either, for the same reason — instant
`setVisible()` toggling only. Since R18 `HomePage.refresh()` keeps the
search text and expanded results, so leaving Home and coming back restores
them; `reset_to_root()` collapses back to the default state. The embedded
page's own `refresh()` only runs while actually expanded (cache-only, cheap —
see `ExplorerPage`'s own docstring — so it's safe to re-run on every expand,
not just the first).

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
import time
from datetime import datetime
from typing import Optional

from retrocheevos.models.account import Account

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.core.activity_feed import build_activity_feed
from retrocheevos.gui import styles
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.components import MetricCard, button, page_title, text_label
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
    library_service,
    notification_service,
    profile_service,
    session_service,
    sync_service,
)
from retrocheevos.widgets.activity_entry_card import ActivityEntryCard
from retrocheevos.widgets.continue_playing_row import NO_EMULATOR_REASON, ContinuePlayingRow
from retrocheevos.widgets.now_playing_panel import NowPlayingPanel

logger = logging.getLogger(__name__)

MAX_CONTINUE_PLAYING_ENTRIES = 50
# Continue Playing and Recent Activity scroll inside panels of this height,
# so the rest of Home (Now Playing, awards) stays reachable below them.
HOME_PANEL_HEIGHT = 360
# Below this page width the 2:1 split and the bottom row stack vertically
# (≈1100 px window with the 220 px sidebar; ScreenDataMapping §6).
STACK_BELOW_WIDTH = 880
SYNC_STATE_POLL_MS = 1000
CONTINUE_PLAYING_EMPTY_TEXT = "Play a game from Library to see it here."
NO_ACCOUNT_TEXT = "Choose an account in the sidebar to see your games."
ACTIVITY_SUBTITLE = "Following · last available RetroAchievements activity"
AWARDS_EMPTY_TEXT = "Sync profile to load awards"
SYNC_NOW_TEXT = "Sync now"
SYNCING_TEXT = "Syncing…"
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
# Opened externally rather than rebuilt in-app: RA exposes no API for this
# ranking, and scraping it isn't something this project does.
BEATEN_GAMES_LEADERBOARD_URL = "https://retroachievements.org/ranking/beaten-games"


def format_last_synced(moment: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Freshness caption for the Home header (ScreenDataMapping §4)."""
    if moment is None:
        return "Never synced"
    now = now or datetime.now()
    seconds = max(0, (now - moment).total_seconds())
    if seconds < 60:
        return "Last synced just now"
    if seconds < 3600:
        return f"Last synced {int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"Last synced {int(seconds // 3600)} h ago"
    return f"Last synced on {moment:%Y-%m-%d}"


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


def _chip(text: str) -> QPushButton:
    """A pill-shaped shortcut button (the board's chips), not a toggle."""
    chip = button(text)
    chip.setProperty("chip", True)
    return chip


# Stable keys used with AppContext's WorkerRegistry so shutdown can cancel
# every background job this page owns, and so "is a job already running?"
# checks don't rely on a dangling QThread reference.
HOME_WORKER_ACTIVITY = ("home", "activity")
HOME_WORKER_PROFILE_SYNC = ("home", "profile-sync")
HOME_WORKER_PLAY = ("home", "play")
HOME_WORKER_SYNC_NOW = ("home", "sync-now")


class HomePage(Page):
    # New profile data landed (opportunistic sync); the sidebar reloads the
    # avatar from it.
    profile_updated = Signal()
    # A destination key for MainWindow ("lists" from the "Your lists" chip).
    navigate_requested = Signal(str)
    # Open the Awards view (D7) as a detail screen.
    awards_requested = Signal()

    def __init__(self, app_context: AppContext) -> None:
        super().__init__(app_context)
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
        # One shared loader for every ContinuePlayingRow built by
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

        self._sync_in_progress = False

        # 1. Header: title, freshness and Sync now (ScreenDataMapping §3.1).
        self._freshness_label = text_label("", "secondary")
        self._sync_status_label = text_label("", "secondary")
        self._sync_now_button = button(SYNC_NOW_TEXT)
        self._sync_now_button.setToolTip("Refresh the displayed account's profile and progress")
        self._sync_now_button.clicked.connect(self._on_sync_now)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(page_title("Home"))
        heading.addWidget(self._freshness_label)
        header = QHBoxLayout()
        header.addLayout(heading)
        header.addStretch(1)
        header.addWidget(self._sync_status_label)
        header.addWidget(self._sync_now_button)
        # Only polled while Home is visible: the job slot has no signal, and
        # the caption's "N min ago" has to move on its own.
        self._sync_state_timer = QTimer(self)
        self._sync_state_timer.setInterval(SYNC_STATE_POLL_MS)
        self._sync_state_timer.timeout.connect(self._update_sync_controls)

        # 2. Catalog search. Typing (or "Explore catalog") reveals the
        # embedded Explorer; its filters and sync bar only show while it is
        # open (R19).
        self._search_input = QLineEdit()
        self._search_input.setObjectName("globalSearch")
        self._search_input.setPlaceholderText("Search the RetroAchievements catalog")
        self._search_input.setAccessibleName("Search the RetroAchievements catalog")
        self._search_input.textChanged.connect(self._on_search_text_changed)
        explore_chip = _chip("Explore catalog")
        explore_chip.clicked.connect(self._on_explore_catalog)
        lists_chip = _chip("Your lists")
        lists_chip.clicked.connect(lambda: self.navigate_requested.emit("lists"))
        search_row = QHBoxLayout()
        search_row.addWidget(self._search_input, stretch=1)
        search_row.addWidget(explore_chip)
        search_row.addWidget(lists_chip)

        self._back_to_home_button = QPushButton("‹ Back to Home")
        self._back_to_home_button.clicked.connect(self._on_back_to_home_clicked)
        self._back_to_home_button.setVisible(False)

        self._explorer_page = ExplorerPage(app_context)
        self._explorer_page.set_results_visible(False)
        self._explorer_page.set_controls_visible(False)
        # Hidden as a whole while collapsed, so its margins leave no gap.
        self._explorer_page.setVisible(False)
        self._explorer_page.sync_finished.connect(self._on_sync_finished)

        # 3. Metrics from the displayed account's synced profile.
        self._metric_points = MetricCard("Points", "Selected account")
        self._metric_true_points = MetricCard("True points", "Selected account")
        self._metric_beaten = MetricCard("Beaten games", "RetroAchievements award status")
        self._metric_mastered = MetricCard("Mastered games", "RetroAchievements award status")
        # The ranking page has no API behind it, so this links out.
        leaderboard = button("Leaderboard ↗", "ghost", compact=True)
        leaderboard.setToolTip("Open the beaten games leaderboard on RetroAchievements")
        leaderboard.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(BEATEN_GAMES_LEADERBOARD_URL))
        )
        for card in (self._metric_points, self._metric_true_points,
                     self._metric_beaten, self._metric_mastered):
            # Top-aligned values whatever each card carries below them.
            card.layout().addStretch(1)
        self._metric_beaten.layout().addWidget(leaderboard, alignment=Qt.AlignmentFlag.AlignLeft)
        self._metrics = QWidget()
        metrics_row = QHBoxLayout(self._metrics)
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(styles.GAP)
        for card in (self._metric_points, self._metric_true_points,
                     self._metric_beaten, self._metric_mastered):
            metrics_row.addWidget(card, stretch=1)

        # 4. Continue Playing | Recent Activity, about 2:1.
        self._continue_playing_container = QWidget()
        self._continue_playing_layout = QVBoxLayout(self._continue_playing_container)
        self._continue_playing_layout.setContentsMargins(0, 0, 0, 0)
        self._continue_playing_layout.setSpacing(styles.SPACE_S)
        self._continue_playing_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._continue_playing_scroll = QScrollArea()
        self._continue_playing_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._continue_playing_scroll.setWidgetResizable(True)
        self._continue_playing_scroll.setWidget(self._continue_playing_container)
        self._continue_playing_group = QGroupBox("Continue Playing")
        self._continue_playing_group.setFixedHeight(HOME_PANEL_HEIGHT)
        QVBoxLayout(self._continue_playing_group).addWidget(self._continue_playing_scroll)

        self._activity_feed_container = QWidget()
        self._activity_feed_layout = QVBoxLayout(self._activity_feed_container)
        self._activity_feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        activity_feed_scroll = QScrollArea()
        activity_feed_scroll.setWidgetResizable(True)
        activity_feed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        activity_feed_scroll.setWidget(self._activity_feed_container)
        self._recent_activity_group = QGroupBox("Recent Activity")
        self._recent_activity_group.setFixedHeight(HOME_PANEL_HEIGHT)
        recent_activity_group_layout = QVBoxLayout(self._recent_activity_group)
        recent_activity_group_layout.addWidget(text_label(ACTIVITY_SUBTITLE, "secondary", wrap=True))
        recent_activity_group_layout.addWidget(activity_feed_scroll)

        self._split = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._split.setSpacing(styles.GAP)
        self._split.addWidget(self._continue_playing_group, stretch=2)
        self._split.addWidget(self._recent_activity_group, stretch=1)
        self._split_widget = QWidget()
        self._split_widget.setLayout(self._split)
        self._split.setContentsMargins(0, 0, 0, 0)

        # 5. Now Playing | Badges and event awards.
        self._now_playing = NowPlayingPanel()
        self._now_playing.progress_updated.connect(self._refresh_continue_playing)
        self.app_context.active_account_changed.connect(self._now_playing.set_account)
        self._now_playing.set_account(self.app_context.active_account)
        self._awards_summary = text_label(AWARDS_EMPTY_TEXT, "secondary", wrap=True)
        self._awards_unread = text_label("", "points", wrap=True)
        self._awards_unread.setVisible(False)
        self._awards_button = button("View awards", compact=True)
        self._awards_button.clicked.connect(self.awards_requested)
        # Shown once a receiver for `awards_requested` exists (MainWindow).
        self._awards_button.setVisible(False)
        self._awards_panel = QGroupBox("Badges and event awards")
        awards_layout = QVBoxLayout(self._awards_panel)
        awards_layout.addWidget(self._awards_summary)
        awards_layout.addWidget(self._awards_unread)
        awards_layout.addStretch(1)
        awards_layout.addWidget(self._awards_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self._bottom = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._bottom.setContentsMargins(0, 0, 0, 0)
        self._bottom.setSpacing(styles.GAP)
        self._bottom.addWidget(self._now_playing, stretch=2)
        self._bottom.addWidget(self._awards_panel, stretch=1)
        self._bottom_widget = QWidget()
        self._bottom_widget.setLayout(self._bottom)

        self._column = QVBoxLayout()
        self._column.setContentsMargins(
            styles.PAGE_PADDING_H, styles.PAGE_PADDING_V - 8,
            styles.PAGE_PADDING_H, styles.PAGE_PADDING_V - 8,
        )
        self._column.setSpacing(styles.GAP)
        self._column.addLayout(header)
        self._column.addLayout(search_row)
        self._column.addWidget(self._back_to_home_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self._column.addWidget(self._explorer_page)
        self._column.addWidget(self._metrics)
        self._column.addWidget(self._split_widget)
        self._column.addWidget(self._bottom_widget)
        self._column.addStretch(1)
        content = QWidget()
        content.setLayout(self._column)
        for container in (self._metrics, self._split_widget, self._bottom_widget):
            container.setProperty("transparent", True)
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page_scroll.setWidget(content)
        self._page_scroll = page_scroll

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page_scroll)
        self._update_sync_controls()

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self._sync_state_timer.start()
        self._update_sync_controls()
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
        self._sync_state_timer.stop()
        self._activity_refresh_timer.stop()

    def _on_active_account_changed(self, account) -> None:
        # R01: cancel anything account-bound before it can land on the wrong
        # user's screen, and drop the cached feed if the user changed.
        self._account_generation += 1
        self.app_context.workers.cancel_key(HOME_WORKER_ACTIVITY)
        self._activity_refresh_pending = False
        self.app_context.workers.cancel_key(HOME_WORKER_PROFILE_SYNC)
        self.app_context.workers.cancel_key(HOME_WORKER_SYNC_NOW)
        new_id = account.id if account is not None else None
        if self._activity_cache_account_id != new_id:
            self._activity_cache = []
            self._activity_entries = []
            self._clear_activity_feed()
            self._activity_cache_account_id = new_id
            self._activity_last_attempt = None
            self._activity_retry_interval_ms = ACTIVITY_REFRESH_INTERVAL_MS
            self._activity_refresh_timer.setInterval(ACTIVITY_REFRESH_INTERVAL_MS)

    def _update_profile_summary(self, stats) -> None:
        """Show `stats` (a `ProfileStats` or None) in the metric cards."""
        self._stats = stats
        if stats is None:
            for card in (self._metric_points, self._metric_true_points,
                         self._metric_beaten, self._metric_mastered):
                card.set_value(None)
            self._metric_mastered.setToolTip("")
        else:
            self._metric_points.set_value(stats.points)
            self._metric_true_points.set_value(stats.true_points)
            self._metric_beaten.set_value(stats.games_beaten)
            self._metric_mastered.set_value(stats.games_mastered)
            self._metric_mastered.setToolTip(
                f"Average completion: {stats.completion_percentage:.1f}%"
            )
        self._update_sync_controls()

    # Sync now ------------------------------------------------------------

    def _update_sync_controls(self) -> None:
        """Freshness caption and Sync now availability (job slot, account)."""
        from retrocheevos.services.job_coordinator import active_job

        account = self.app_context.active_account
        stats = getattr(self, "_stats", None)
        if account is None:
            self._freshness_label.setText("No account selected")
        else:
            self._freshness_label.setText(
                format_last_synced(stats.last_synced_at if stats is not None else None)
            )
        own_sync = self._sync_in_progress or self.app_context.workers.has_key(
            HOME_WORKER_PROFILE_SYNC
        )
        running = active_job()
        if own_sync:
            self._sync_now_button.setText(SYNCING_TEXT)
            self._sync_now_button.setEnabled(False)
            self._sync_status_label.setText("")
        elif running is not None:
            self._sync_now_button.setText(SYNC_NOW_TEXT)
            self._sync_now_button.setEnabled(False)
            self._sync_status_label.setText(f"{running} is running")
        else:
            self._sync_now_button.setText(SYNC_NOW_TEXT)
            self._sync_now_button.setEnabled(account is not None)
            if self._sync_status_label.property("kind") != "error":
                self._sync_status_label.setText("")

    def _set_sync_error(self, message: str) -> None:
        self._sync_status_label.setProperty("kind", "error" if message else None)
        self._sync_status_label.setText(message)

    def _on_sync_now(self) -> None:
        """Forced profile sync under the app-wide job slot (R03)."""
        from retrocheevos.services.job_coordinator import (
            JOB_SYNC_PROFILE, release, try_acquire,
        )

        account = self.app_context.active_account
        if account is None or self.app_context._shutting_down:
            return
        token = try_acquire(JOB_SYNC_PROFILE)
        if token is None:
            self._update_sync_controls()
            return
        self._set_sync_error("")
        self._sync_in_progress = True
        try:
            gen, account_id = self._account_generation, account.id
            client = session_service.build_api_client(account)
            worker = ServiceWorker(sync_service.sync_profile, client, account, cancellable=True)
            worker.finished_ok.connect(
                lambda _result: self._on_sync_now_done_guarded(gen, account_id)
            )
            worker.failed.connect(
                lambda message: self._on_sync_now_failed_guarded(message, gen, account_id)
            )
            worker.finished.connect(lambda: self._on_sync_now_finished(token))
            self.app_context.workers.start(worker, key=HOME_WORKER_SYNC_NOW)
        except Exception:
            self._sync_in_progress = False
            release(token)
            raise
        self._update_sync_controls()

    def _sync_result_is_current(self, generation: int, account_id: int) -> bool:
        account = self.app_context.active_account
        return (
            generation == self._account_generation
            and account is not None
            and account.id == account_id
        )

    def _on_sync_now_done_guarded(self, generation: int, account_id: int) -> None:
        if not self._sync_result_is_current(generation, account_id):
            return
        library_service.purge_missing_roms()
        self.refresh()
        self.profile_updated.emit()

    def _on_sync_now_failed_guarded(self, message: str, generation: int, account_id: int) -> None:
        if self._sync_result_is_current(generation, account_id):
            self._set_sync_error("Sync failed — showing cached data")
            self._sync_status_label.setToolTip(message)

    def _on_sync_now_finished(self, token) -> None:
        from retrocheevos.services.job_coordinator import release

        release(token)
        self._sync_in_progress = False
        self._update_sync_controls()

    def reset_to_root(self) -> None:
        """Clear the catalog search and collapse its results.

        Used by "Back to Home", by selecting Home again in the sidebar and on
        account changes; plain navigation keeps the search (R18).
        """
        self._search_input.blockSignals(True)
        self._search_input.clear()
        self._search_input.blockSignals(False)
        self._explorer_page.set_search_text("")
        self._collapse_explorer()

    def refresh(self) -> None:
        self._now_playing.set_account(self.app_context.active_account)
        # The search and the embedded Explorer's results, filters, sorting
        # and scroll are kept (R18). Re-query them from the cache when
        # expanded so a sync made elsewhere shows up.
        if self._results_expanded():
            self._explorer_page.refresh()
        # The filter pills are on screen even while results are hidden, so
        # the Console pill needs its list now — `_expand_explorer`'s own
        # `refresh()` would populate it too, but only after the user has
        # already opened the pill and found it empty.
        self._explorer_page.load_consoles()
        self._clear_continue_playing()
        # Recent Activity is deliberately *not* cleared here. It's the only
        # section backed by several seconds of live API calls, and wiping it
        # on every navigation back to Home meant staring at "Loading…" each
        # time for data that was already correct. `_refresh_activity_feed`
        # below decides whether to show that placeholder.

        account = self.app_context.active_account
        if account is None:
            self._update_profile_summary(None)
            self._refresh_awards_summary()
            self._show_continue_playing_message(NO_ACCOUNT_TEXT)
            # Dropped on logout/account switch, or the next account would
            # briefly see the previous one's feed painted from cache.
            self._activity_cache = []
            self._activity_entries = []
            self._activity_cache_account_id = None
            self._clear_activity_feed()
            return

        self._update_profile_summary(profile_service.get_profile_stats(account.id))

        # Opportunistic, not periodic: only checked here, on activation/
        # revisit of Home, never on a timer. Cheap no-op if `profile_stats`
        # is still fresh (`sync_service.PROFILE_SYNC_STALE_AFTER`) — self-heals
        # stale points (e.g. `true_points` stuck at its migration-v8 backfill
        # default of 0) without hammering the API on every restart/switch.
        # Same in-flight guard as the activity fetch.
        self._start_profile_sync(account)

        # Continue Playing lists installed ROMs too, so it needs the same
        # sweep the Library does — otherwise a game deleted from disk keeps
        # showing here even after the Library has dropped it.
        library_service.purge_missing_roms()
        self._refresh_continue_playing()
        self._refresh_awards_summary()
        # Re-show what we already have straight away, then refresh behind it.
        # Only a cold start (nothing cached, or the account changed) gets the
        # "Loading…" placeholder.
        if self._activity_cache:
            self._render_activity_entries(self._activity_cache)
        self._refresh_activity_feed(show_loading=not self._activity_cache)

    def _refresh_awards_summary(self) -> None:
        """Counts for the awards panel; the lists live in the Awards view."""
        account = self.app_context.active_account
        if account is None:
            self._awards_summary.setText(AWARDS_EMPTY_TEXT)
            self._awards_unread.setVisible(False)
            return
        badges = profile_service.list_badges(account.id)
        events = sum(1 for badge in badges if badge.is_event)
        regular = len(badges) - events
        if badges:
            self._awards_summary.setText(
                f"{regular} {'badge' if regular == 1 else 'badges'} · "
                f"{events} event {'award' if events == 1 else 'awards'}"
            )
        else:
            self._awards_summary.setText(AWARDS_EMPTY_TEXT)
        unread = len(notification_service.list_unread_events(account.id))
        self._awards_unread.setText(f"{unread} new {'event' if unread == 1 else 'events'}")
        self._awards_unread.setVisible(unread > 0)

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
        self._refresh_awards_summary()

    def _refresh_continue_playing(self) -> None:
        """Rebuilds just the Continue Playing list.

        Split out of `refresh()` so launching a game can re-sort the list
        (the launch stamps `last_played_at`, which drives the ordering)
        without also re-triggering the several-second Recent Activity fetch
        and the profile sync that a full `refresh()` would.
        """
        self._clear_continue_playing()

        account = self.app_context.active_account
        if account is None:
            self._show_continue_playing_message(NO_ACCOUNT_TEXT)
            return

        console_names = {console.id: console.name for console in console_service.list_consoles()}
        emulator_consoles = {config.console_id for config in library_service.list_emulator_configs()}

        # One combined sequence — matched games and unmatched-ROM fallbacks
        # interleaved, sorted by recency, then progress, then title.
        entries: list[tuple[Optional[datetime], Optional[float], str, object]] = [
            (entry.last_played_at, entry.percent_complete, entry.game.title, entry)
            for entry in dashboard_service.get_continue_playing_games(account.id)
        ]
        entries += [
            (rom.last_played_at, None, derive_title_from_filename(rom.file_path), rom)
            for rom in dashboard_service.get_unmatched_continue_playing_roms(account.id)
        ]
        entries.sort(key=_continue_playing_sort_key)
        # Capped *after* sorting, so the ones kept are the most recent; the
        # Library is the full list.
        entries = entries[:MAX_CONTINUE_PLAYING_ENTRIES]
        if not entries:
            self._show_continue_playing_message(CONTINUE_PLAYING_EMPTY_TEXT)
            return

        cover_guesses = library_service.guess_games_for_unmatched_roms()
        for _last_played, percent_complete, _title, item in entries:
            console_id = item.console_id if isinstance(item, InstalledRom) else item.game.console_id
            reason = None if console_id in emulator_consoles else NO_EMULATOR_REASON
            if isinstance(item, InstalledRom):
                row = ContinuePlayingRow(
                    self._image_loader,
                    console_name=console_names.get(item.console_id),
                    rom=item,
                    cover_game=cover_guesses.get(item.id),
                    play_unavailable_reason=reason,
                )
                row.play_requested.connect(self._on_play_unmatched_rom)
                row.remove_requested.connect(self._on_remove_unmatched_rom)
            else:
                row = ContinuePlayingRow(
                    self._image_loader,
                    console_name=console_names.get(item.game.console_id),
                    game=item.game,
                    achievements_unlocked=item.achievements_unlocked,
                    achievements_total=item.achievements_total,
                    percent_complete=percent_complete,
                    play_unavailable_reason=reason,
                )
                row.play_requested.connect(self._on_play)
            self._continue_playing_layout.addWidget(row)

    def _show_continue_playing_message(self, text: str) -> None:
        self._clear_continue_playing()
        self._continue_playing_layout.addWidget(text_label(text, "secondary", wrap=True))

    def continue_playing_rows(self) -> list[ContinuePlayingRow]:
        rows = []
        for index in range(self._continue_playing_layout.count()):
            widget = self._continue_playing_layout.itemAt(index).widget()
            if isinstance(widget, ContinuePlayingRow):
                rows.append(widget)
        return rows

    def _on_remove_unmatched_rom(self, installed_rom_id: int) -> None:
        library_service.remove_installed_rom(installed_rom_id)
        self._refresh_continue_playing()

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Stack the two-column rows in narrow windows (ScreenDataMapping §6)."""
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if self.width() < STACK_BELOW_WIDTH
            else QBoxLayout.Direction.LeftToRight
        )
        if self._split.direction() != direction:
            self._split.setDirection(direction)
            self._bottom.setDirection(direction)

    def is_stacked(self) -> bool:
        return self._split.direction() == QBoxLayout.Direction.TopToBottom

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
        # The search field stays; metrics, the two panels and the bottom
        # row give way to the catalog results and their filters.
        for widget in (self._metrics, self._split_widget, self._bottom_widget):
            widget.setVisible(False)
        self._continue_playing_group.setVisible(False)
        self._back_to_home_button.setVisible(True)
        self._explorer_page.setVisible(True)
        self._explorer_page.set_controls_visible(True)
        self._explorer_page.set_results_visible(True)
        self._column.setStretchFactor(self._explorer_page, 1)
        # Cache-only ("must feel instant"), so re-running it on every expand
        # keeps results fresh if a sync happened elsewhere.
        self._explorer_page.refresh()

    def _collapse_explorer(self) -> None:
        self._explorer_page.set_results_visible(False)
        self._explorer_page.set_controls_visible(False)
        self._explorer_page.setVisible(False)
        self._column.setStretchFactor(self._explorer_page, 0)
        self._back_to_home_button.setVisible(False)
        self._continue_playing_group.setVisible(True)
        for widget in (self._metrics, self._split_widget, self._bottom_widget):
            widget.setVisible(True)

    def _on_explore_catalog(self) -> None:
        if not self._results_expanded():
            self._expand_explorer()
        self._search_input.setFocus()

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
        self.reset_to_root()

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
            self.profile_updated.emit()

    def _on_profile_sync_failed(self, message: str) -> None:
        # Never surfaced to the user (e.g. `QMessageBox`) — this is a
        # best-effort background refresh, not a user-initiated action; the
        # manual "Sync Profile" button on the Profile page is what reports
        # failures. Just log for diagnosis.
        logger.info("Opportunistic profile sync skipped/failed: %s", message)
