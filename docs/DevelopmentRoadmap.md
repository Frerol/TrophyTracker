# RetroCheevos — Development Roadmap

## Current Status

- Explorer filter/grid performance — resolved (superseded by the table
  redesign below, which replaced the Game Card grid entirely).
- Explorer redesigned to match RetroAchievements' own site — pill-style
  filter bar (`widgets/explorer_filter_bar.py`) above a sortable
  `QTableView` (`gui/models/explorer_table_model.py` +
  `gui/delegates/explorer_delegates.py`), replacing the side filter panel
  and virtualized Game Card grid. Added a real cover-art download/cache
  pipeline (`library/game_images.py`, `services/image_service.py`,
  `gui/image_loader.py`).
- Explorer actions column (Play/+) rewritten from real per-row
  widgets (`QTableView.setIndexWidget()`) to a hand-painted
  `ActionsDelegate` (`gui/delegates/explorer_delegates.py`), after
  `setIndexWidget()` was implicated in a native crash
  (`STATUS_FATAL_USER_CALLBACK_EXCEPTION` inside `Qt6Widgets.dll`,
  reproduced identically across PySide6 6.11.1 and 6.10.1) triggered by
  entering fullscreen from Explorer. The whole table is now plain
  paint-only `QAbstractItemView` virtualization with zero widget-pool
  bookkeeping. **Confirmed fixed on real hardware** — PySide6 stays pinned
  to 6.10.1 in `requirements.txt` for now (not yet restored to latest).
- Block/hide-game feature: a game can be blocked from Explorer's "+" menu
  (`gui/delegates/explorer_delegates.py`'s `_show_menu`, after a separator —
  a different kind of action than the progress-tracking list items above
  it), which hides it everywhere (Explorer, Dashboard's Continue Playing,
  and every other list's view) until manually unblocked from a dedicated
  "Blocked Games" list in Settings. Implemented as `ListType.BLOCKED`, not
  a new table — `user_lists.list_type` has no CHECK constraint and already
  had the exact UNIQUE index blocking needs, so `add_to_list`/
  `remove_from_list`/`get_games_in_list` all work generically with zero new
  repository code. New `core/lists.py` holds the one real rule (a blocked
  game disappears from *other* lists it's already a member of, not just
  new results). See `docs/Database.md` §4.1.
- `RemovableListDelegate` (`gui/delegates/removable_list_delegate.py`):
  paints an inline "−" remove control per row on Settings' simple
  management lists (ROM Folders, Emulators, ROM Destinations, Blocked
  Games), reusing the same paint-and-`editorEvent()` technique as
  `ActionsDelegate` rather than `QListWidget.setItemWidget()` — the same
  `QAbstractItemView` widget-embedding mechanism already implicated in the
  Explorer crash above, deliberately not reintroduced even at this small,
  low-risk scale. Existing "Remove Selected"-style buttons kept working
  unchanged alongside it.
- Quick Links per console: one reference URL per console (`models/quick_link.py`,
  `database/repositories/quick_link_repository.py`, `console_quick_links`
  table, migration 6), managed in Settings (mirrors `EmulatorConfig`/
  `RomDestination`'s exact upsert shape) and opened externally via
  `QDesktopServices.openUrl` from a new "Quick Link" button next to
  Library's console selector — the app never fetches the URL itself. Also
  serves as the answer to "integrate a homebrew catalog": researched
  itch.io, PDRoms, Homebrew Hub, and Internet Archive — no single API
  covers homebrew across this app's ~84 consoles, so a small curated
  suggestion table (`library/quick_link_suggestions.py`) pre-fills a good
  default per console with real sources where they exist, rather than
  building a separate scraping/browsing subsystem.
- Event Badges: investigated whether a full Events feature (dates/
  deadlines/countdowns) was buildable — it isn't, RA's API has no
  structured data for that, only forum posts. What's real: (1) `Events` is
  a synced console (id 101) whose games are just normal games — synced via
  the existing per-console sync flow (confirmed live: 237 games appeared,
  Explorer/completion-progress worked with zero new code), (2)
  `API_GetUserAwards.php`'s `AwardType` field (confirmed live, previously
  discarded entirely — see `api/profile.py`) categorizes each badge.
  `core/mapping.py::map_badge` now computes `Badge.is_event`: known
  `AwardType` values (`"Game Beaten"`, `"Mastery/Completion"`) are normal,
  anything else is an event badge, reinforced by cross-checking the
  award's console against the Events console — defensive by design, since
  this account had zero event/site awards to directly confirm the exact
  "event" string against. `gui/pages/profile_page.py` now splits badges
  into two tabs (Badges / Event Badges) on that flag. No dates, no
  notifications — matches what the API can actually support.
- **Unified Home screen** (`gui/pages/home_page.py`), RA-site-inspired,
  built in phases (thin skeleton first, matching how the Explorer redesign
  started). Phases 1-4 are done and verified on real hardware:
  - **Phase 1 — skeleton**: logo (`assets/logo.png`, background-stripped
    from the user's source JPEG) + app name top-left, top bar, 3-section
    sidebar, added as a new nav entry, no cutover of existing pages.
  - **Phase 2 — real data**: Continue Playing, points, and Event Badges
    wired in, reusing `dashboard_service`/`profile_service` as-is, zero
    new backend.
  - **Phase 3 — navigation/menu**: user menu (Profile/Library/Lists/
    Settings/Logout), plus Recent Activity absorbed from the now-deleted
    `DashboardPage`. `main_window.py`'s nav converged onto one
    `QStackedWidget` via two paths — the primary `_nav_list`
    (Home/Explorer/Leaderboards) and the user menu
    (`HomePage.navigate_requested`/`logout_requested` signals,
    `_menu_pages` dict). New `session_service.logout()` /
    `AccountRepository.deactivate_all()`.
  - **Phase 4 — Recent Activity redesign + header polish**: Recent
    Activity rebuilt to match RA's own "Following" page — avatar,
    last-activity time, current game, an aggregate achievements/playtime
    line, and a colored rich-presence status line, for the account itself
    plus every followed user in one sorted list (no Message/Unfollow/
    Block buttons). Confirmed live that RA's API supports this:
    `API_GetUsersIFollow.php`, and `API_GetUserProfile.php`/
    `API_GetUserRecentAchievements.php`/`API_GetGameInfoAndUserProgress.php`
    all work for `u=<any username>`, not just the authenticated account.
    `services/activity_feed_service.py` is a deliberate departure from
    every other `services/` module — a **live read with no DB write**,
    since rich presence is ephemeral and caching it would just show stale
    status. Entries stream in via `ServiceWorker`'s `stream_results`/
    `partial_result` (a second generic capability alongside the existing
    `report_progress`/`progress`) instead of waiting for the whole
    several-second fetch, and a real `.failed` handler now shows an error
    label instead of leaving "Loading…" stuck forever.
    **Known, disclosed fidelity gap vs. RA's site**: no true "last seen"
    timestamp (only `MemberSince`) and no per-category achievement
    breakdown — approximated with last-unlock-time and an aggregate
    `{unlocked}/{total} achievements | Played {Hh MMm}` line.
    Header redesign: user menu button is now a photo-only
    `_HoverMenuButton` (no name) — click opened Profile back then, hover
    (after a short delay, auto-closing when the cursor leaves both the
    button and the menu) opens the full destinations menu. Points are
    stacked vertically (blue/white, no parentheses, vertically centered
    against the avatar via `top_bar.setAlignment(points_column,
    AlignVCenter)`). `main_window.py` gained always-visible browser-style
    back/forward buttons above `_nav_list` (`_history`/`_history_index`,
    `_show_page` as the single funnel every navigation path goes
    through — nav and menu pages alike). Window/taskbar icon set from a
    dedicated square `assets/icon.png` (Pillow-generated from the non-
    square `logo.png`, which stays Home-header-only) via `setWindowIcon`,
    plus `ctypes.SetCurrentProcessExplicitAppUserModelID` in `main.py` so
    Windows doesn't show python.exe's icon in the taskbar.
    **Two real bugs found and fixed during this phase**, both instructive
    for future GUI work in this app: (1) a *native access-violation
    crash* — `main_window.py` was calling `HomePage.refresh()` twice in
    immediate succession on several paths (redundant explicit calls,
    and `itemClicked` + `currentRowChanged` both firing for one click);
    harmless while every worker was fast, but once Recent Activity's
    live fetch made `_activity_worker` slow, the second `refresh()` call
    reliably destroyed a still-running `QThread` — undefined behavior in
    Qt. Fixed by making every navigation path call `refresh()` exactly
    once (`itemClicked` connection removed, `_on_logout` uses the
    `blockSignals` dance `_on_menu_navigate` already used), plus a
    defense-in-depth "skip if already running" guard on both workers.
    (2) `QLayout.setSpacing()` does **not** support negative values —
    confirmed via direct `.geometry()` measurement that any negative
    spacing (tested -1 through -20) is silently discarded and replaced
    with the platform style's own default (~6px), identical regardless of
    how negative the argument was; `0` is the true floor. Several rounds
    of "make the arrows/points closer together" produced zero visible
    change for exactly this reason until this was found and both
    `HISTORY_BUTTON_SPACING`/`POINTS_SPACING` were corrected to `0` (plus
    a missing `points_column.setAlignment(AlignTop)`, without which a
    taller sibling widget in the same row caused Qt to distribute unused
    height *between* the two point labels even at zero spacing).
- **Phase 5 — Explorer embedded in Home's expand-on-click search bar**:
  done and verified. Chosen mechanism: **in-layout expand**, not an
  overlay (manual `move()`/`resize()` geometry is itself the class of
  code implicated in Explorer's earlier native crash) and not a
  `QStackedWidget` page switch (would be a pseudo-navigation with no real
  page backing it). `HomePage`'s center column's old disabled placeholder
  became `_search_launcher_button` — a plain trigger, not a real search
  field. Clicking it hides the launcher + Continue Playing + Recent
  Activity and shows a **second, independent `ExplorerPage` instance**
  (`self._explorer_page`) with `stretch=1`; a "‹ Back to Home" button
  reverses it. `HomePage.refresh()` always collapses back to the default
  state — the embedded page's own state isn't remembered across Home
  visits.
  **Component reuse**: `ExplorerPage`/`ExplorerFilterBar`/
  `ExplorerTableModel`/the three delegates are **completely unmodified**
  — `ExplorerPage` was already a fully self-contained `QWidget` needing
  only an `AppContext`, so it's constructed a second time directly in
  `HomePage.__init__` and just added to a different layout. Deliberate
  tradeoff: two independent `ExplorerPage` instances (the standalone nav
  one in `MainWindow`, this new embedded one) means separate table/filter
  state — an action in one isn't reflected in the other until each
  re-fetches. Reparenting a single shared instance between containers
  was considered and rejected: that's exactly the kind of geometry/
  parent-change operation this phase was trying to avoid touching.
  No animation on expand/collapse either, same reasoning — instant
  `setVisible()` only.
  **Testing**: headless — expand/collapse toggles visibility correctly,
  `ExplorerPage.refresh()` fires exactly once per expand (re-runs every
  expand, not just the first, since it's cache-only/cheap per its own
  docstring), 25 expand/collapse cycles with no exception,
  `HomePage.refresh()` collapses even if left expanded, sorting/filtering/
  `ActionsDelegate` hit-testing all work correctly against the real
  synced database (1778 rows) while embedded. One incidental finding
  investigated and ruled out: an abrupt test-script exit while
  `ImageLoader`'s background `QThreadPool.globalInstance()` thumbnail
  loads were still in flight logged `RuntimeError: Signal source has been
  deleted` — confirmed via a controlled rerun (`waitForDone()` before
  exit) that this is a pre-existing test-harness artifact of the global
  thread pool outliving a short-lived script, not something
  expand/collapse causes (collapsing only hides the page, never destroys
  it or its `ImageLoader`).
  **The actual historical crash trigger, reproduced directly**: a
  real-platform (non-offscreen) driven script expanded the embedded
  Explorer, entered/exited fullscreen twice (`showFullScreen()`/
  `showNormal()` — the literal action that caused the original
  `setIndexWidget()` crash), resized the window four times while
  expanded, and round-tripped through standalone-Explorer-nav and back —
  `logs/crash.log` line count unchanged throughout. Also confirmed with
  the standard real 20s app launch used all session.
- **Next up**: Phase 6/7 (Games Beaten + Friends leaderboards — needs a
  research spike, this pulls forward Version 1.2 work with zero backend
  built), Phase 8 (notification bell — own feasibility check, same
  data-gap pattern as "recently added achievements"). Separately, also
  still pending: restoring PySide6 to latest (pinned to 6.10.1 since the
  Explorer crash, confirmed fixed independent of version, never actually
  re-tested against latest).

## MVP

- Core (project scaffolding, layered architecture wiring)
- Database (SQLite schema per `Database.md`)
- API (RetroAchievements client: auth, games, achievements, median time to
  beat — per `API.md`)
- Settings (API Key, Username, Accounts, ROM folders)
- Explorer (search + filters, Game Cards, Installed status)
- Profile content (stats, badges, event awards, recent activity) — on Home;
  the standalone Profile page was later removed
- Library (manual ROM matching/organization, no auto-scan yet)
- Lists (Want to Play, Playing, Completed, Abandoned)
- Dashboard (Continue Playing, Recent activity; Recommendations shown as an
  empty placeholder until the v1.1 engine lands — see Version 1.1)
- Search
- Filters

## Version 1.1

- Recommendations engine (history, genres, completion, console preference,
  median time to beat)
- Notifications (achievements released, new supported games, badges,
  events — opt-in, no spam)
- Watch Folder (automatic scanning on folder change)
- ROM Scanner (automatic hashing + matching, automatic organization)
- Recent activity summary (Dashboard) — covers the Events and Recently added
  achievements sections deferred from MVP (no achievement-added timestamp in
  the schema, no Events endpoint modeled yet); named separately from the
  full Events feature in Version 1.2 to avoid confusing the two

## Version 1.2

- Leaderboards (RetroAchievements leaderboards, Friends, Daily/Weekly/
  All Time, custom Games Beaten leaderboard)
- Badges (full owned/missing/progress view, auto-updated)
- Events
- Downloads — only if legally possible; falls back to Watch Folder only if
  direct download isn't feasible

## Version 2.0

- Steam Deck support
- Linux support
- Plugin system

For unscheduled/backlog ideas, see `FutureIdeas.md`.

## Process Note

Per `Vision.md` (Development Workflow):

- Architecture, product design, UX, and technical decisions originate in
  planning (ChatGPT).
- Claude Code handles implementation, refactoring, testing, and module
  creation — strictly following `Architecture.md`, `Database.md`, `API.md`,
  and `UI.md`, never inventing architecture or deviating from the
  documented project structure.
- Recommended order of operations: review/confirm this documentation set →
  scaffold folder structure → implement module by module (Database → API →
  Core → Services → GUI), MVP scope first.
