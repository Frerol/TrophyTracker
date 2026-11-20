# TrophyTracker — Development Roadmap

The planned Android achievement-tracking companion has a separate
[roadmap](AndroidRoadmap.md). It excludes ROM management and emulator launching.

## Priority technical backlog — code review 2026-11-20

Treat this work as a priority ahead of new feature phases. P1 addresses
correctness and stability first; P2 addresses performance and reliability;
P3 strengthens maintenance and release verification. Within each tier,
follow the order below. These are open tasks, not implemented fixes.

Review covered the desktop GUI/worker lifecycle, Explorer read path, API
client/sync orchestration, SQLite repositories, ROM scanning and artwork.
Evidence below is from code inspection unless explicitly described as
executed. GUI risks still require reproduction with PySide6; the review
environment does not have it installed. No production database or live API
was used, and no application behavior was changed.

### P1 — correctness and stability

- [x] **R01 — Reject stale account-bound worker results.**
  `gui/pages/home_page.py::refresh` clears the activity cache only when
  there is no active account, rather than keying it by account ID.
  `_on_activity_entry_ready`, `_on_activity_feed_ready` and
  `_on_photo_ready` accept results without checking the originating account.
  A direct account switch can retain the previous feed; an old in-flight
  request can repopulate it even after logout. Capture account ID and a
  request generation, invalidate cached data on account changes, and reject
  stale partial/final/error/photo callbacks. **Done when:** delayed results
  from account A cannot update B's Home or a logged-out Home, and B can
  refresh after A's request finishes. Add deterministic regression coverage.

- [x] **R02 — Coordinate cancellation and application shutdown.**
  `gui/workers.py::ServiceWorker` has no cooperative cancellation contract;
  `gui/main_window.py::closeEvent` only saves window state. Sync loops and
  their sleeps can run long after a close request. Inspect and reproduce
  shutdown with active sync, scan, activity and image tasks, then add shared
  worker ownership, cancellation checks between units of work, interruptible
  waits and orderly teardown without blocking the GUI for a full sync.
  Include `gui/image_loader.py`'s global pool and signal-object lifetime.
  **Done when:** closing during each operation produces no destroyed-running-
  QThread or deleted-signal errors and committed sync progress remains usable.

- [x] **R03 — Coordinate syncs across pages and share API pacing.**
  `gui/pages/explorer_page.py::_set_sync_buttons_enabled` protects only one
  page instance; Home embeds another Explorer and Settings/Home also start
  sync workers. Multiple jobs can therefore bypass those local guards.
  `services/sync_service.py` and `services/activity_feed_service.py` pace
  requests independently, while `api/client.py::get` has no shared limiter.
  Introduce application-wide job coordination and a shared request budget,
  with consistent bounded retry/backoff and handling of retry guidance when
  supplied by the server. Do not simply increase request concurrency.
  **Done when:** simultaneous triggers from Home, Explorer and Settings
  cannot launch conflicting jobs, and mocked 429s preserve progress without
  retry storms or SQLite write contention.

- [x] **R04 — Detect changed ROMs at previously scanned paths.**
  `services/library_service.py::scan_rom_folder` skips every path already
  recorded before inspecting file changes. Replacing a ROM at the same
  path can leave its old hash and game association indefinitely. Store and
  compare a file fingerprint (size and high-resolution modification time),
  rehash changed files, invalidate affected artwork, and offer a forced
  verification pass for same-fingerprint replacements. **Done when:** an
  unchanged rescan avoids hashing, a modified file is rematched, and manual
  matches have an explicit preservation/review policy.

- [x] **R13 — Make migrations atomic and recoverable; provide verified backups.**
  Follow-up review: `database/migrations.py::apply_migrations` executes DDL
  without an explicit transaction boundary and only commits after the loop.
  With the current sqlite3 connection defaults, early DDL can survive a
  later failure even when the caller rolls back. An isolated in-memory
  experiment injected `CREATE TABLE` followed by invalid SQL: after rollback,
  the table still existed while `PRAGMA user_version` remained zero. This
  demonstrates a partial-schema risk, not a failure observed in user data.
  Define explicit migration transactions covering schema changes and version
  updates, roll back and close failed initialization connections, and reject
  databases newer than the application supports. Before upgrades, create a
  consistent SQLite backup using the backup API rather than copying a live
  WAL database file. Add a documented restore path and retention policy;
  distinguish local backups from portable exports and exclude credentials
  from portable exports, since the database can contain fallback API keys.
  **Done when:** injected failures leave schema/data/version consistent,
  upgrades from representative populated older schemas preserve user data,
  a second startup succeeds after recovery, and a restored backup passes
  integrity/foreign-key checks and retains lists, manual matches and settings.

- [x] **R14 — Reconcile credential-vault changes with database commits.**
  `database/repositories/account_repository.py::add` writes to the OS vault
  before executing the account upsert; `remove` deletes the vault entry
  before its caller commits. A later SQL/commit failure can therefore leave
  the database rolled back but credentials changed or removed. The
  `credential_store.delete_key` docstring incorrectly assumes the rows are
  already gone at this point. Define recoverable sequencing and compensation
  for these two independent stores, retaining the existing fallback behavior
  when the vault is unavailable and making deferred cleanup retryable.
  **Done when:** injected vault, SQL and commit failures during account
  creation, key replacement and removal do not silently lose the last usable
  credential or leave an unexplained mismatch; tests verify recovery and
  diagnostics without exposing keys.

- [x] **R15 — Record last-played time only after successful process creation.**
  `services/library_service.py::_launch_installed_rom` updates and commits
  `last_played_at` before calling `launch_emulator`. An invalid executable
  or permission error therefore moves an unlaunched game into recent play.
  Create the emulator process first, then record the successful launch;
  handle a subsequent persistence failure separately so the UI does not
  imply that an already-running emulator failed to start or invite a
  duplicate launch. **Done when:** mocked `Popen` failures leave recency and
  play-session state unchanged, successful creation records them once, and
  a database failure after creation reports the actual partial outcome.

### P2 — performance and resilience

- [ ] **R05 — Restore indexed ROM hash lookup.**
  `database/repositories/game_repository.py::find_game_id_by_hash` always
  uses `LOWER(hash) = LOWER(?)`. The v23 normalization migration does not
  make this expression use the ordinary `idx_game_hashes_hash` index,
  despite the comment in `database/schema.py`. An isolated in-memory SQLite
  `EXPLAIN QUERY PLAN` confirmed `SCAN game_hashes` for the current query
  versus `SEARCH ... USING INDEX idx_game_hashes_hash` for plain equality.
  Use normalized equality with a compatibility fallback, or an index whose
  expression/collation matches the lookup. Correct the misleading comments.
  **Done when:** mixed-case compatibility tests pass, the normal query uses
  an index, and a representative bulk-match benchmark records the effect.

- [ ] **R06 — Reduce synchronous Explorer refresh work.**
  `gui/pages/explorer_page.py::set_search_text` immediately runs
  `_refresh_results` on Home search changes. That path queries and converts
  all matching games, filters them in Python in `core/explorer.py`, reads
  all account completion records, recounts the catalog and resets the model.
  Debounce typing first; measure catalog-sized refreshes before deciding
  whether to move the read to a worker, push predicates into a repository
  query, or page results. Preserve Core's filtering rules and both Explorer
  instances. **Done when:** record query count and input-to-render timings
  against a representative catalog, reduce redundant refreshes, and retain
  blocked/completed/list/installed filter semantics and sorting behavior.

- [ ] **R07 — Make artwork caching atomic, retryable and bounded.**
  `library/game_images.py::download_image` writes directly to the final
  shared cache path; `gui/image_loader.py` deduplicates only within one
  loader. Concurrent page instances can request/write the same cover.
  `_ImageLoadTask.run` also lacks the exception/final-signal protection
  present in `_RomImageLoadTask.run`. In
  `gui/models/explorer_table_model.py`, a failed load caches `None` for the
  model's lifetime, and successful pixmaps have no eviction policy.
  Use temporary downloads plus atomic replacement, shared in-flight
  deduplication, guaranteed completion cleanup, expiring failure entries
  and a measured memory budget. **Done when:** interrupted/concurrent
  downloads leave no partial final file, exceptions release pending entries,
  offline-to-online retries recover covers, and long browsing stays bounded.

- [ ] **R08 — Isolate activity failures and avoid repeated full rebuilds.**
  `services/activity_feed_service.py::get_recent_activity_feed` aborts the
  entire user loop if a summary fetch fails; only the progress subrequest
  has per-user recovery. Each streamed result also rebuilds every activity
  widget in `HomePage._render_activity_entries_now`. Handle individual-user
  failures while retaining good entries, propagate authentication/rate-limit
  failures appropriately, and batch or incrementally update rendering.
  Preserve existing refresh backoff and last-good data behavior.
  **Done when:** one unavailable followed user does not discard other users,
  partial failure is distinguishable from complete success, and initial
  streaming avoids repeated teardown of unchanged cards.

- [ ] **R09 — Stream folder traversal and expose progress sooner.**
  `services/library_service.py::scan_rom_folder` uses
  `sorted(folder_path.rglob("*"))`, materializing the whole directory tree
  before scanning the first file. It also traverses directories later
  discarded by the non-ROM filter. Use streaming traversal and prune only
  directories whose exclusion is established by the existing rules; report
  discovery progress and allow cancellation. **Done when:** large nested
  folders begin reporting work before enumeration ends, use bounded
  traversal memory, and retain current supported-format discovery.

- [ ] **R10 — Remember completed empty metadata fetches.**
  `GameRepository.list_ids_missing_hashes` explicitly treats a successful
  empty hash response as never fetched; `list_ids_missing_median_time`
  similarly selects every NULL median. Repeated backfills can spend API
  requests on the same legitimate empty results. Track fetch outcome/time
  separately from the value, with an expiry/force-refresh policy; failures
  must remain retryable. **Done when:** an immediate second backfill skips
  successful empty results, retries failed requests and refreshes expired
  entries without confusing unknown duration with zero duration.

### P3 — maintenance and release verification

- [ ] **R11 — Automate reproducible checks and validate dependency changes.**
  The repository has unittest coverage but no checked-in CI workflow or
  development-tool configuration discovered in this review. Add documented
  test commands and CI for core/services/database plus offscreen GUI tests,
  with Windows/Linux packaging smoke checks. Separate reproducible release
  dependency constraints from deliberate upgrade testing. Reuse the
  existing pending task to re-test the PySide6 pin rather than upgrading
  it without crash regression checks. **Done when:** a fresh environment
  can run the checks, supported platforms are exercised, and GUI/framework
  upgrades repeat fullscreen, navigation and worker-lifetime scenarios.

- [ ] **R12 — Reconcile historical roadmap status with current code.**
  The historical Current Status below still describes Quick Links,
  `ProfilePage`, `DashboardPage` and fixed list behavior that no longer
  match the current modules/UI; README already describes newer Now Playing,
  account isolation and artwork work. Preserve useful investigation history
  but label it as historical, replace stale next steps and link current
  behavior to the actual files. **Done when:** one current status section
  reflects the shipped code, distinguishes desktop/Android scope and points
  to this prioritized backlog without presenting removed features as active.

Review validation: 22 existing tests passed using
`PYTHONPATH=src python3 -m unittest tests.api.test_credential_redaction tests.database.test_game_hash_case tests.library.test_zip_extraction`.
This targeted run does not validate the GUI or establish performance numbers;
the only executed performance-related check was the isolated SQLite query plan.

Follow-up validation (2026-11-20): R13's failure-injection experiment used
only an in-memory database and temporarily replaced the migration list in
that Python process. R14 and R15 are code-inspection findings; their failure
scenarios still require regression tests during implementation. R13–R15 are
additional P1 work and precede P2 despite their later review IDs.

## Desktop interface revamp — proposed R16–R27

**Status:** proposals only; no UI implementation is implied by this section.
These items cover the entire desktop experience, including secondary pages,
menus and dialogs. Android retains its separate roadmap. The technical backlog
above keeps priority; visual work must preserve R01–R04 and R13–R15 and address
R06/R07/R08 before increasing catalog, artwork or activity rendering work.

### Visual direction and scope

Aim for a modern achievement companion with the familiarity of RetroAchievements:
clear game identity, prominent achievement badges and progress, compact catalog
browsing, and a readable social feed. Reference the public
[RetroAchievements home](https://retroachievements.org/) and
[game catalog](https://retroachievements.org/gameList.php) during design;
record dated screenshots of the relevant pages in R16. Public references do not
establish the appearance of authenticated pages. No login is needed for planning.

Proposed direction to explore: graphite/charcoal surfaces, restrained amber/gold
accents for achievement milestones, a distinct primary-action color, larger
covers where they aid recognition, quieter borders, and stronger typography and
spacing hierarchy. Treat this as a candidate palette to compare against the
current ink/mint theme in `gui/styles.py`, rather than a claim about exact site
colors. Preserve TrophyTracker's name and identity. Use existing/licensed artwork
and a consistent icon set; do not depend on emoji for navigation or status.

A complete revamp includes Home, embedded Explorer, Library, Lists, Settings,
account menus, ROM matching/emulator dialogs and update feedback. It does not
promise new leaderboards, event calendars, chat, recommendations or website-only
features without their own data/feasibility work. Use existing services and
cached data first; represent unavailable information honestly. Keep PySide6
Widgets/model-view as the baseline; a framework rewrite is outside this scope.

### Foundation

- [ ] **R16 — Audit the current experience and define the target layouts.**
  Inventory current screens, shared widgets, inline styles, duplicated controls
  and navigation flows in `gui/main_window.py`, `gui/pages/` and `widgets/`.
  Capture baseline screenshots and representative tasks: sign in, search,
  filter, launch, assign a ROM, manage a list and switch accounts. Produce
  annotated desktop layouts for every destination and a before/after comparison
  for Home and Explorer, including empty/offline examples. Document what is
  reused versus replaced and reconcile the proposed navigation with `UI.md`.
  **Done when:** one design specification maps every current action to its new
  location, contains a candidate palette/type scale and small-window variants,
  and identifies API/data gaps separately from visual changes.

- [ ] **R17 — Build a shared visual system and reusable primitives.**
  Expand `gui/styles.py` into semantic tokens for surfaces, text, accents,
  borders, spacing, typography, radii, icon sizes and progress states. Standardize
  page/section headers, buttons, search fields, filter chips, status labels,
  panels, menus and dialogs. Migrate inline styles as each screen is converted;
  include hover, pressed, selected, disabled, focus and error states. Use bundled
  or dependable system fonts with a defined fallback and license any new assets.
  **Done when:** a component preview demonstrates all states and the same
  controls look consistent on Windows/Linux, without adding page-specific color
  literals or replacing meaningful labels with icons alone.

- [ ] **R18 — Unify the application shell, navigation and search.**
  Consolidate the brand header, account controls and page navigation in
  `gui/main_window.py` and `home_page.py`. Prototype a persistent compact sidebar
  with a collapsible narrow-window variant and one global search entry. Preserve
  Home's embedded Explorer as the default search/results flow unless R16
  explicitly documents a replacement; do not introduce a second independent
  search/filter state. Show account identity and sync state consistently, with
  direct access to Library, Lists and Settings. Avoid placeholder destinations.
  **Done when:** navigation, back-to-Home, logout and account switching remain
  synchronized; returning from a game or another page restores filters,
  selection and scroll, and the shell fits at 1024×720 without clipped actions.

### Main screens

- [ ] **R19 — Redesign Home around play, progress and activity.**
  Give Now Playing a clear primary position when a session is active; otherwise
  prioritize Continue Playing and a useful first action. Design a compact player
  summary with avatar, points and distinctly labeled Beaten/Mastered/Completion
  values, a coherent badge gallery and a readable activity column. Use covers
  and typographic hierarchy instead of a stack of equally prominent group boxes.
  Reflow secondary content below the main column in smaller windows; cap artwork
  loading to visible content. Reuse `now_playing_panel.py`,
  `continue_playing_game_row.py` and `activity_entry_card.py` where practical.
  **Done when:** no-account, no-history, active-session, partial-activity-error
  and offline states all have intentional layouts; late account-bound results
  cannot repopulate another account's screen, and refresh preserves good data.

- [ ] **R20 — Modernize Explorer while retaining fast catalog browsing.**
  Refresh `explorer_filter_bar.py`, `explorer_table_model.py` and
  `explorer_delegates.py`: a clear search/results header, legible active-filter
  chips, reset action, result count, consistent cover sizing, aligned metadata
  and obvious Play/list actions. Retain a compact sortable table as the default.
  A richer cover view is optional only after R06/R07 measurements demonstrate
  acceptable responsiveness and bounded memory; implement it using model/view
  virtualization rather than one widget per game. Preserve existing filtering,
  blocked/completed behavior, manual matching and sort semantics.
  **Done when:** typing and filtering retain the measured R06 responsiveness,
  keyboard selection survives refresh, all actions are discoverable without
  hover alone, and fullscreen/resize do not reintroduce the `setIndexWidget()`
  native-crash path. No catalog-wide eager artwork fetch is introduced.

- [ ] **R21 — Add a coherent game-detail presentation.**
  Design a focused detail panel or page reached consistently from Home,
  Explorer, Library and Lists. Show cover, title, console, available progress,
  local-ROM status and the relevant Play, match, list and open-on-RA actions.
  Start with existing cached fields; expose achievement-level content only
  where existing services support it, with a separately scoped fetch if needed.
  Distinguish unknown duration/progress from zero. Keep a clear return path;
  do not change which catalog games are eligible merely to populate the panel.
  **Done when:** matched, unmatched, uninstalled and offline examples work;
  missing artwork has a stable fallback, launching uses the existing guarded
  flow, and returning restores the originating view rather than resetting it.

- [ ] **R22 — Rework Library and ROM-management interactions.**
  Unify console selection, installed-game presentation, unmatched-ROM handling,
  cover customization and scan controls in `library_page.py` and its widgets.
  Use coherent cover proportions and an explicit matched/unmatched/missing-file
  status with contextual actions. Separate routine play from file-management
  actions. Redesign `match_rom_dialog.py` and `find_emulator_dialog.py` using the
  shared components, with helpful explanations when no candidate/config exists.
  **Done when:** scanning shows progress/cancellation without freezing the page,
  manual matches and account isolation are preserved, and empty folders, missing
  emulators, ambiguous matches and failed launches each offer a useful next step.

- [ ] **R23 — Give Lists a consistent collection experience.**
  Redesign `lists_page.py` and `list_entry_row.py` with clear list selection,
  item counts, covers, console labels and available progress. Make switching,
  renaming, removing an entry and deleting an entire list visually distinct;
  keep destructive actions explicit. Reuse the same game actions/detail entry
  points as Explorer and Library. Only add sorting/filter controls supported by
  existing data, retaining selection and scroll during updates.
  **Done when:** predefined/custom/empty lists all have usable layouts, existing
  memberships and blocked-game rules remain intact, and deleting a list cannot
  be confused with deleting a ROM or removing an account.

- [ ] **R24 — Organize Settings, onboarding and account management.**
  Replace a long undifferentiated settings surface with clear groups or
  subnavigation for Accounts, Library/Folders, Emulators, Appearance and About/
  Updates as supported by the application. Give first-run setup a short guided
  path: add RA credentials, choose a folder, configure an emulator; keep optional
  steps skippable and settings reachable afterward. Use readable form labels,
  inline validation and explicit save/outcome feedback; mask API keys. Bring
  menus, confirmations and `update_banner.py` into the shared visual system.
  **Done when:** a first-time user can reach a playable matched game without
  guessing where configuration lives, multiple accounts remain distinguishable,
  and credential/backend failures retain the existing recovery behavior.

### Cross-cutting quality and delivery

- [ ] **R25 — Standardize feedback, loading and recovery states.**
  Define shared presentations for initial loading, refreshing cached content,
  empty results, no account, offline, partial success, retryable error and
  destructive confirmations. Use stable placeholders rather than layout jumps,
  show freshness where useful, and reserve blocking dialogs for decisions that
  need them. Consolidate background job progress so it stays understandable
  across page changes. Preserve cancellation and shared API pacing.
  **Done when:** every redesigned page has documented state examples; retries
  respect backoff, errors preserve useful cached content, and a started emulator
  with failed recency persistence is never reported as a failed launch.

- [ ] **R26 — Validate accessibility, scaling and interaction polish.**
  Audit keyboard order, shortcuts, visible focus, accessible names, text contrast
  and status labels across the shell, tables, menus and dialogs. Target at least
  4.5:1 contrast for normal text and 3:1 for large text and meaningful UI
  boundaries; do not encode completion, selection or errors by color alone.
  Check 100/125/150/200% scaling, long game titles, missing fonts and layouts
  from 1024×720 through 1920×1080. Keep optional motion short and disableable;
  avoid expensive shadows/animations in lists. Compact/comfortable density is
  optional only if both modes can be maintained consistently.
  **Done when:** search → select → details → launch and account/settings flows
  work entirely by keyboard; enlarged text does not hide actions, icons remain
  legible, and animation does not block input or trigger extra network work.

- [ ] **R27 — Deliver the revamp incrementally with visual regression checks.**
  Convert one complete flow at a time using the shared components; keep account,
  list and ROM data compatible, without a destructive reset. Add deterministic
  screenshot fixtures with synthetic data and focused interaction tests for
  navigation, selection and loading/error states. Repeat fullscreen, resize,
  active-worker close and account-switch scenarios; measure refresh latency,
  artwork memory and activity rendering against the technical-backlog baselines.
  Review Windows packaging and Linux AppImage with the bundled fonts/icons and
  no developer cache. Reconcile `UI.md`, `Branding.md` and README screenshots
  after the final layouts land; remove superseded styles/widgets.
  **Done when:** all destinations and dialogs use the new system, both packaged
  platforms pass startup/navigation smoke checks, and the measured revamp has
  no unexplained performance or worker-lifetime regression.

### Suggested implementation order

1. R16 defines layouts and navigation; R17 establishes shared components.
2. R18 establishes the shell; R19 and R20 convert the main browsing/play flow,
   coordinated with R06/R07/R08; R21 unifies its game-detail destination.
3. R22–R24 convert Library, Lists, Settings, onboarding and secondary dialogs.
4. Apply R25/R26 to each converted flow, rather than postponing state handling
   and accessibility until the end. R27 consolidates regression/release checks
   and documentation throughout delivery, with a final full-interface review.

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

### R13–R15 recovery follow-up (2026-11-20)

Implemented the review corrections: mandatory verified pre-upgrade backups,
collision-free backup names, account-service transaction boundaries, durable
vault-deletion intents with retry and re-add protection, and metadata reads
before emulator process creation. Recency persistence/rollback failures after
creation preserve the running session and return the started process.

Recovery/retention and portable-export procedures are documented in
[Database.md](Database.md#9-upgrade-recovery-backups-and-portable-exports).
Regression coverage lives in `tests/database/test_recovery.py`,
`tests/services/test_account_recovery.py` and `tests/services/test_launch_recovery.py`.
Validation: 197 non-GUI tests passed, including 23 new recovery tests. The eight
GUI test modules and `test_wii_rvz_scan.py` require PySide6, unavailable in this
environment, and were excluded from this run. No live API, real vault or user
database was used.
