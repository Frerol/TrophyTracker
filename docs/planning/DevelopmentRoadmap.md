# TrophyTracker — Development Roadmap

Last reconciled: 2026-11-20. Status describes the documented implementation;
validation results are recorded evidence, not new checks run on each edit.
Completed review details and earlier planning history live in
[RoadmapHistory.md](../archive/RoadmapHistory.md).

## Roadmap at a glance

| Track | Status | Next action |
| --- | --- | --- |
| [Desktop interface revamp, R16–R27](#active-desktop-plan--interface-revamp-r16r27) | R16 done; R17 mostly done; R18–R27 planned | Review the component preview; decide D1; start R18 (sidebar shell). |
| [Desktop integration, R28–R30](#desktop-integration--r28r30) | Planned, after the revamp | Wait for R27; then start R28 (tray mode). |
| [Platform and maintenance](#platform-and-maintenance) | R11 partially open | Exercise interactive use on native Windows; keep PySide6 at 6.10.1. |
| [Reliability and performance, R01–R15](#completed-technical-review--r01r15) | Done except R11 | Preserve regression coverage. |
| Android companion | Planned; no app or APK | Run Phase 0 of the [Android roadmap](AndroidRoadmap.md). |

Checked items have local implementation and regression evidence; this does not
imply validation on every native platform. Unchecked items are planned.

## Next releases

Version numbers and scope below are proposals until the release is prepared,
except where marked confirmed. Changes since the last release are
collected in the `Unreleased` section of [CHANGELOG.md](../../CHANGELOG.md),
as described in `AGENTS.md`.

| Release | Proposed scope | Status |
| --- | --- | --- |
| 0.1.0 | First TrophyTracker release; Linux x86_64 AppImage | Published |
| Next minor (0.2.0) | R16–R27 interface revamp, released once R27 passes | Confirmed (2026-11-20): published only after the full revamp. In development; `APP_VERSION` is already 0.2.0, so local test builds carry that number. |
| Following minor (0.3.0) | R28–R30 desktop integration: tray mode, summary popup, local session signals | Proposed |
| Windows package | Depends on R11's interactive Windows validation | Undecided ([D3](#open-decisions)) |

## Open decisions

These items wait on a product decision rather than on implementation work.

| ID | Decision | Blocks | Current position |
| --- | --- | --- | --- |
| D1 | Final application icon: brand concept A (pixel trophy) or C (cartridge with pixel trophy), and how they combine | R17 brand sub-items, R27 packaging assets | Preference for A and C; recommendation is A for small icons and C as the larger variant, not yet selected. B is a documented alternative. |
| D3 | Whether and when to publish a Windows package | Windows release | Experimental build helper only; needs R11 interactive validation first. |
| D4 | PySide6 upgrade | Dependency updates | Stay on 6.10.1; 6.12.0 crashes at interpreter teardown in the upgrade probe. |
| D5 | Revive features cut by the proposal review (ranking, rarity, release year, global totals, near-mastery, instant unlock notifications) | Nothing in R16–R30 | Out of scope; tracked in [FutureIdeas.md](FutureIdeas.md). Each needs its own data contract. A delayed notification for locally detected unlocks is a separate idea that builds on R30. |
| D6 | Which emulators get local log adapters first (R30) | R30 adapters beyond the first | RetroArch first, since it covers the most consoles; others follow the R30 investigation. |

### Resolved decisions

| ID | Decision | Outcome (2026-11-20) | Applied to |
| --- | --- | --- | --- |
| D2 | Ship the `Unreleased` fixes as a 0.1.x patch before the revamp, or fold them into 0.2.0 | No patch release. The fixes ship with 0.2.0 after the full revamp. | Next releases |
| D7 | Where to show badges and event awards, which are synced but never displayed | An **Awards** view reached from Home, combining the account's badges and the current Events list (with the new-events banner). Needs a badge read method in `ProfileRepository`. | R19 |
| D8 | Per-mode achievement counts on cards, or a labeled combined count | Cards keep RetroAchievements' **combined count**, labeled "achievements" and never "hardcore". Game and achievement details are per mode. Revisit per-mode card counts only if R21 confirms a hardcore count from the API. | R19, R20, R22, R23 |
| D9 | Library's "No achievement set" filter | Replaced by **Unmatched** ("no catalog match; progress unavailable"), because a game without a set cannot be told apart from an unmatched ROM locally. | R22 |

## Current Status

Reflects the shipped desktop code as of 2026-11-20. The R16–R27 revamp is
planned, not implemented.

### Desktop (this repository)

- **Navigation** — `gui/main_window.py` hosts four persistent destinations:
  Home, Library, Lists and Settings. There is no standalone Profile or
  Dashboard page.
- **Home** — `gui/pages/home_page.py`: Continue Playing, points/true points,
  beaten/mastered/completion stats, Events (event games with progress and a
  new-events banner), Recent Activity (`services/activity_feed_service.py`),
  Now Playing (`widgets/now_playing_panel.py`, `services/now_playing_service.py`)
  and an always-visible search field that expands an embedded
  `ExplorerPage` (`gui/pages/explorer_page.py`) in place. Badges are synced
  and stored but not displayed anywhere
  ([ScreenDataMapping.md](../design/ScreenDataMapping.md) F1).
- **Explorer** — `gui/pages/explorer_page.py` with the sortable table
  (`gui/models/explorer_table_model.py`) and paint-only delegates
  (`gui/delegates/explorer_delegates.py`); no `setIndexWidget()` widget pool.
- **Library** — `gui/pages/library_page.py`: installed-ROM grid, per-account
  ROM folders, background scanning and manual matching.
- **Lists** — `gui/pages/lists_page.py` over `core/lists.py`; blocked games are
  `ListType.BLOCKED`, not a separate table.
- **Settings** — `gui/pages/settings_page.py`: accounts, emulators and profile
  sync.
- **Per-account data** — `rom_folders` and `installed_roms` are account-scoped
  (migration v21); signing out preserves each account's library and lists.
- **Artwork** — `library/game_images.py`, `library/rom_artwork.py`,
  `gui/image_loader.py` and `services/image_service.py`, with the bounded cache
  from R07.
- **Recovery** — `database/backup.py` and `database/migrations.py` implement
  atomic migrations, verified backups and credential/launch recovery (R13–R15).
- **Validation** — performance evidence is in
  [PerformanceValidation.md](../validation/PerformanceValidation.md); test
  commands, CI jobs and the dependency policy are in
  [Testing.md](../validation/Testing.md). The latest recorded full suite run
  passed 323 tests on Linux and Windows hosted CI.

### Removed or superseded (not active)

- Quick Links per console and ROM Destinations — tables dropped in schema v20.
- `ProfilePage` — content lives on Home and Settings ([UI.md](../design/UI.md) §3.4).
- `DashboardPage` — retired; Recent Activity moved to Home.
- Watch Folder organizer and automatic file moving — scans only index what is
  already on disk.
- Fixed list behavior — lists are definitions in `user_list_definitions`.

Do not reintroduce these based on the historical record.

## Active desktop plan — interface revamp R16–R27

**Status:** planned; nothing in this section is implemented.

**References:** the [reviewed UI proposal](../design/ui-proposal-reviewed.html)
(eight boards: Home, Library, Game detail, Achievement detail, Explorer, Lists,
Settings, Brand) and the [product fit review](../design/ProposalReview.md). The
[original proposal](../design/ui-proposal.html) is preserved as source
material, not a feature contract. All boards use synthetic data at 1240×780;
no sample value is a production default.

**Constraints for every item:**

- Keep PySide6 Widgets and model/view; the HTML preview does not imply a
  framework migration.
- Preserve the account, credential, launch and matching safeguards (R01–R04,
  R13–R15) and the performance work (R05–R10). Compare new rendering against
  [PerformanceValidation.md](../validation/PerformanceValidation.md).
- Never fabricate data: missing metrics are shown as unavailable, unknown is
  not zero, and hardcore/softcore counts are never combined.
- Follow [ScreenDataMapping.md](../design/ScreenDataMapping.md) for each
  screen's data sources and states. Card counts on every screen use the
  combined, labeled count from D8.
- Apply R25 (states) and R26 (accessibility and scaling) to each screen as it
  is converted, not only at the end.

### Visual direction

Dark purple surfaces, gold achievement/progress accents, turquoise secondary
highlights, rounded panels and restrained typography. Keep the
**TrophyTracker** name. The board's light outer background is presentation
chrome, not the application theme.

| Role | Reference value |
| --- | --- |
| Application background | `#14121C` |
| Sidebar background | `#0F0D16` |
| Panel surface | `#1E1B2B` |
| Selected navigation / secondary controls | `#2A2540` |
| Progress track | `#2E2A44` |
| Muted badge / outline example | `#3A3555` |
| Primary text | `#ECE9F5` |
| Secondary text | `#A9A4BD` |
| Gold: achievements, progress and primary actions | `#F5B83D` |
| Turquoise: secondary highlights | `#3DD6C3` |

Typography: **Inter** for interface text, **Space Grotesk** for headings,
prominent numbers and branding. Reference sizes: 28 px page headings, 16 px
section headings, 32 px metrics, 14 px body/control text, 13 px secondary text.
Shapes: 12 px panel radii, 8 px control/cover radii, pill-shaped filters.
Controls: 44 px standard buttons, 40 px compact Play buttons, 36 px chips.
Layout: 220 px sidebar, 28×32 px main padding, 16 px card gaps. These are
baselines to scale and validate, not fixed limits. Colored initial-letter
covers are mockup placeholders; production uses cached artwork with fallbacks.

Navigation is **Home, Library, Lists, Settings**, with the displayed account in
the sidebar. Home search enters the Explorer catalog; Library search stays
local. Game and achievement details are contextual screens. Standalone
Achievements/Systems destinations from the original proposal are not required.

### Foundation

- [x] **R16 — Complete the screen/action/data mapping.**
  Delivered in [ScreenDataMapping.md](../design/ScreenDataMapping.md)
  (2026-11-20), starting from `ProposalReview.md`.
  - [x] Inventory every current action and dialog (§2).
  - [x] Map the eight boards to widgets, services and fields (§3).
  - [x] Confirm retained features: Home catalog search, local Library search,
    Lists, Now Playing, events, matching, artwork, explicit account selection
    and emulator controls. Library must not inherit Explorer's suggestion
    exclusions. Badges turned out not to be displayed today (F1, D7).
  - [x] Define game/account/hardcore/softcore scopes, data freshness and
    unknown/error states (§4).
  - [x] Specify the on-demand game detail and unlock service dependencies (§5).
  - [x] Map small-window variants and dialogs (§2.7, §6).

  **Done when:** every retained action has a route, data source and failure
  state; detail contracts are explicit; synthetic reference data never becomes
  an application default. The decisions it raised (D7–D9) are resolved; the API
  fields marked "to verify" in §5 are checked when R21 starts.

- [ ] **R17 — Implement the visual system and the brand assets.**
  Token, component, font and preview work landed on 2026-11-20; see
  [Branding.md](../design/Branding.md#visual-system-r17).
  - [x] Translate the palette, type scale, spacing and proportions into
    semantic tokens in `gui/styles.py`. The current screens already use the
    new palette through legacy aliases.
  - [x] Standardize sidebar items, metric cards, game cards, achievement rows,
    progress bars, search, chips, buttons, menus and dialogs, including hover,
    focus, pressed, disabled and selected states (`gui/components.py`).
  - [x] Bundle licensed fonts with fallbacks so packaging works offline
    (`assets/fonts/`, PyInstaller spec).
  - [x] Build a component preview covering all states
    (`tools/preview/component_preview.py`).
  - [ ] Maintainer review of the component preview.
  - [x] Compare brand concepts A and C at 16/24/32 px and larger sizes on
    Linux, on dark and light backgrounds, with the wordmark (preview
    `--brand-sheet`).
  - [ ] Repeat the brand comparison on a native Windows taskbar.
  - [ ] *(Blocked on [D1](#open-decisions))* Produce the selected icon and
    variant rules, wordmark and packaging assets; document licenses in
    `Branding.md`. Do not choose a concept silently or use emoji as icons.

  **Done when:** the component preview is reviewed, D1 is decided and the
  brand assets are documented. The token and component work may land before D1.

### Screens

- [ ] **R18 — Build the sidebar shell and reconcile navigation/search.**
  - [ ] Home, Library, Lists and Settings with selected-item treatment and the
    displayed account/avatar; no nonfunctional placeholders.
  - [ ] Account selection and sign out; saved credentials never change the
    displayed account on their own.
  - [ ] Detail routes keep the originating view's state.

  **Done when:** all destinations and empty states work; back restores search,
  filters, selection and scroll; account controls stay synchronized; the shell
  adapts from 1240×780 down to 1024×720 without clipping actions.

- [ ] **R19 — Rebuild Home.**
  - [ ] Header with last-sync freshness and Sync now.
  - [ ] Points, True points, Beaten games and Mastered games from the selected
    account's existing profile data.
  - [ ] Continue Playing and Recent Activity in a roughly 2:1 split, with
    covers, progress and guarded Play. Recent Activity stays followed-user
    activity, not an unlock event stream.
  - [ ] Keep Now Playing and catalog search.
  - [ ] Add the Awards view (D7): the account's badges and event awards from
    a new `ProfileRepository` read method, plus the current Events list and
    new-events banner.
  - [ ] Card counts are RetroAchievements' combined count, labeled
    "achievements" (D8).

  **Done when:** real or cached data drives the screen; no-account, no-history,
  active-session, offline and partial-feed variants work; narrower windows
  reflow; R08 card reuse, backoff, last-good data and account guards remain.

- [ ] **R20 — Adapt Explorer to the visual system.**
  - [ ] Restyle the table, filter chips, result count, reset, metadata and
    Play/list controls. The cover grid belongs to Library (R22), not Explorer.
  - [ ] Follow R16's mapping for Home search and game detail entry.
  - [ ] Preserve blocked/completed rules, numeric sorting, keyboard selection
    and return-state restoration.

  **Done when:** all current catalog actions remain discoverable; R06
  worker/debounce/sorting and R07 artwork budget remain intact; catalog scope is
  clearly distinct from Library; resizing and fullscreen avoid the
  `setIndexWidget()` crash path.

- [ ] **R21 — Deliver game and achievement details.**
  - [ ] Game summary: game/system, cover, per-mode unlocked/total and points,
    progress, Play, configured emulator and ROM path.
  - [ ] Achievement list and individual screen: title, description, badge,
    points; All/Unlocked/Missing filters; supported sorting such as points.
  - [ ] Account- and mode-aware on-demand data and cache refresh before
    enabling controls.
  - [ ] Community discussion opens externally. Out of scope: publishing,
    replies, translation, RetroPoints, rarity, author, global unlocks and
    release year.
  - [ ] Entry from Home, Explorer, Library and Lists with Play/match/list/RA
    actions preserved.

  **Done when:** filters and counts use verified data; matched, unmatched,
  uninstalled, no-set and offline states work; images stay bounded; back
  restores the source view.

- [ ] **R22 — Implement the Library grid and management handoffs.**
  - [ ] Indexed-ROM context, manual scan, local search, All/In progress/
    Mastered/Unmatched (D9) and System filters.
  - [ ] Adaptive four-column reference grid with covers, console, progress and
    guarded Play/configuration, using model/view virtualization within R07's
    artwork budget.
  - [ ] Distinguish unmatched ROMs from unknown progress.
  - [ ] Keep selected/all scans, forced hash verification, manual matching,
    cover customization and missing-file feedback.
  - [ ] Share folder and emulator editors with Settings.

  **Done when:** account-scoped search and filters work; scans keep discovery
  progress and cancellation; manual matches and launch recovery survive; empty
  libraries, missing emulators, ambiguous matches and failed scans offer next
  steps.

- [ ] **R23 — Apply the collection design to Lists.**
  - [ ] Restyle list selection/counts, create/rename/delete, membership
    removal, Play and detail entry over existing definitions.
  - [ ] Custom lists stay supported; sample names such as Backlog/Favorites do
    not become mandatory defaults. Blocked stays special.

  **Done when:** memberships and blocked-game rules are preserved, selection and
  scroll survive updates, and list removal cannot be confused with deleting ROM
  files or removing the account.

- [ ] **R24 — Implement Settings, onboarding and account controls.**
  - [ ] Accounts, Synchronization, ROM folders and Emulator configuration
    sections; keep existing dialogs. Move Explorer's catalog sync actions
    into Synchronization (ScreenDataMapping F7). Settings has no
    appearance, window or update controls today (F6); window state stays
    automatic and the update banner stays in the shell.
  - [ ] Short, skippable first-run flow: RA credentials, explicit account
    choice, ROM folder and emulator.
  - [ ] Keep masked keys, save/outcome feedback, account-removal consequences
    and full emulator arguments/core/discovery/Flatpak options.
  - [ ] Do not add startup scanning, fixed five-minute polling or instant
    unlock notifications.

  **Done when:** a first-run user can reach a playable game; all current
  settings remain accessible; saved credentials never switch the account
  silently; offline assets and credential/backend recovery keep working.

### Cross-cutting quality and delivery

R25 and R26 are checklists applied to each screen from R18–R24; their
sub-items close per screen.

- [ ] **R25 — States and feedback.**
  For each destination: initial loading, cached refresh, empty, no-account,
  offline, partial-success, retryable-error and destructive-action states.
  - [ ] Shell and Home
  - [ ] Explorer
  - [ ] Game and achievement details
  - [ ] Library
  - [ ] Lists
  - [ ] Settings and onboarding

  Rules: sync freshness in the Home header; scan/job progress visible across
  navigation; distinguish no achievements, locked achievements, missing
  metadata and zero progress; stable placeholders instead of layout jumps;
  blocking dialogs only for real decisions; cancellation, shared API pacing and
  R10 empty-fetch/expiry behavior preserved.
  **Done when:** every destination has state examples; retries respect backoff;
  failures keep useful cached content; an emulator that started despite failed
  recency persistence is never reported as a failed launch.

- [ ] **R26 — Accessibility, scaling and interaction.**
  - [ ] Keyboard order, shortcuts, visible focus and accessible names on every
    converted screen.
  - [ ] Contrast of reference colors: at least 4.5:1 for normal text and 3:1
    for large text and meaningful boundaries; document token adjustments.
  - [ ] Locked, mastered, selected and error states do not rely on color alone.
  - [ ] 100/125/150/200% scaling, long titles, missing fonts, and layouts from
    1024×720 through 1920×1080.
  - [ ] Motion is short and can be disabled; no costly shadows or animations in
    large grids.

  **Done when:** search → select → detail → Play and account/settings flows
  work by keyboard; scaled text leaves actions visible; brand icons stay legible
  at small sizes; animation creates no extra network work.

- [ ] **R27 — Final verification and cleanup.**
  - [ ] Deterministic screenshots with synthetic fixtures compared with the
    eight boards; differences from real data, accessibility and responsive
    layout documented.
  - [ ] Secondary dialogs converted.
  - [ ] Account, list and ROM data preserved without a destructive reset.
  - [ ] Fullscreen, resize, active-worker close and account-switch scenarios
    repeated.
  - [ ] Catalog/grid latency, artwork memory and activity rendering measured
    against R05–R10 baselines.
  - [ ] Windows package and Linux AppImage smoke-tested with bundled fonts and
    icons and no developer cache.
  - [ ] `UI.md`, `Branding.md` and README screenshots updated; superseded
    styles and widgets removed.

  **Done when:** all destinations and actions work in the new system, both
  packaged platforms start and navigate correctly, and performance or lifetime
  differences are explained.

### Implementation order

1. R16 mapping, then R17 tokens and components. The brand sub-items run in
   parallel once D1 is decided.
2. R18 shell; then R19 Home and R22 Library, coordinating R20's Explorer
   handoff with both.
3. R21 details with their data dependencies; then R23 Lists and R24 Settings.
4. Apply R25/R26 to each converted screen; keep R27 screenshot and performance
   evidence current and finish with the full desktop and package review.

## Desktop integration — R28–R30

**Status:** planned; starts after the R16–R27 revamp so the popup uses the new
visual system.

**Goal:** closing the window keeps TrophyTracker running in the system tray,
and a click on the tray icon shows a compact RetroAchievements summary, while
spending as few API requests as possible.

**Constraints for every item:**

- Reuse `services/now_playing_service.py`, the profile services and the shared
  API pacing (R03); do not add a second tracking pipeline.
- Do not read emulator memory or evaluate achievement logic locally. The
  emulator's own rcheevos integration remains the source of unlocks; this
  track only observes signals the emulator already exposes.
- A locally detected unlock is not proof that RetroAchievements recorded it.
  Show it as detected until the API confirms it.
- Background API policy:
  - no configured emulator running: no background requests; opening the popup
    shows cached data and refreshes only if it is stale;
  - emulator running: one request when the game is identified, to cache its
    achievements and artwork; then one confirmation request per locally
    detected unlock, or a spaced refresh with backoff when no local adapter
    exists;
  - never a fixed short polling interval.

- [ ] **R28 — Tray mode and background lifecycle.**
  - [ ] System tray icon with a context menu: Open TrophyTracker, Sync now,
    displayed account and Quit.
  - [ ] Closing the window hides it to the tray. Enabled by default, with a
    Settings option to quit on close instead.
  - [ ] The first time the window is hidden, a system notification explains
    that TrophyTracker is still running in the tray.
  - [ ] When no tray is available (`QSystemTrayIcon.isSystemTrayAvailable()`
    is false, for example stock GNOME or Steam Deck game mode), closing the
    window quits as it does today.
  - [ ] Quit from the tray goes through the existing bounded shutdown (R02).
  - [ ] Release artwork caches and Explorer results while only the tray is
    active.
  - [ ] Apply the background API policy above.

  **Done when:** close-to-tray, reopen and quit work on Windows, KDE and a
  desktop without a tray; no background request is made while no emulator is
  running; workers still shut down cleanly from the tray; memory while hidden is
  measured and lower than with the window open.

- [ ] **R29 — Tray summary popup.**
  A single click on the tray icon opens a compact popup.
  - [ ] **Game active:** cover, title, console, hardcore/softcore mode,
    unlocked/total achievements, points, rich presence text, achievements
    unlocked in this session and when the data was last checked. Actions: open
    game detail and open TrophyTracker.
  - [ ] **No game active:** the displayed account's own activity: points,
    recently unlocked achievements and recently played games, plus Continue
    Playing with guarded Play so a game can start without opening the main
    window. Followed-user activity stays in the main window.
  - [ ] No-account, offline, stale-cache and API-error states, following R25.
  - [ ] Keyboard access and contrast following R26.
  - [ ] Position the popup near the tray icon where the platform allows it;
    on Wayland, where positioning is not available, use a predictable
    placement and document it.

  **Done when:** both states show real or cached data with visible freshness;
  Play from the popup launches through the existing launch safeguards (R15);
  the popup opens instantly from cache and refreshes within the API policy;
  behavior is verified on Windows, X11 and Wayland.

- [ ] **R30 — Local session signals from emulators.**
  Start with an investigation; build adapters only where the signal proves
  reliable.
  - [ ] Detect whether a configured emulator process is running, including one
    started outside TrophyTracker, without API requests.
  - [ ] Investigate the signals each supported emulator exposes: log lines for
    login, loaded game and achievement unlocks, and RetroArch's network command
    interface for the loaded content. Record formats, required settings
    (for example, logging enabled) and version differences.
  - [ ] Implement a log adapter for the first emulator chosen in
    [D6](#open-decisions); unsupported or unrecognized emulators fall back to
    the API path.
  - [ ] Unlocks detected locally appear in the popup immediately as detected,
    then as confirmed after the API confirmation request.

  **Done when:** the investigation is documented; process detection works for
  native, AppImage and Flatpak emulators; the first adapter detects unlocks
  from recorded sample logs in tests; a missing, rotated or unrecognized log
  degrades to the API path without errors.

## Platform and maintenance

- [ ] **R11 — Reproducible checks and platform validation.**
  Done: CI workflow (`.github/workflows/ci.yml`), hash-locked dependencies,
  packaging smoke probe and GUI lifecycle regressions. Hosted run
  `44840664571` (commit `baf3079`) passed the full suite (323 tests) on Linux
  and Windows × Python 3.12/3.13 and started the frozen bundle on both
  platforms. See the
  [completion audit](../validation/RoadmapCompletionAudit.md#r11--hosted-ci-evidence-2026-11-20).
  - [ ] Remaining: interactive use on a native Windows desktop (real display,
    not offscreen).
- **PySide6 pin** — stays at 6.10.1. The non-blocking upgrade probe passed all
  GUI regressions with 6.12.0 but crashed during interpreter teardown on both
  platforms. Re-run the probe and follow [Testing.md](../validation/Testing.md)
  before changing the pin ([D4](#open-decisions)).

## Completed technical review — R01–R15

Full defect descriptions, acceptance criteria and validation notes are in
[RoadmapHistory.md](../archive/RoadmapHistory.md#technical-review--r01r15); the
[completion audit](../validation/RoadmapCompletionAudit.md) records findings
and follow-up evidence.

| ID | Item | Status |
| --- | --- | --- |
| R01 | Reject stale account-bound worker results | Done |
| R02 | Coordinate cancellation and application shutdown | Done |
| R03 | Coordinate syncs across pages and share API pacing | Done |
| R04 | Detect changed ROMs at previously scanned paths | Done |
| R05 | Restore indexed ROM hash lookup | Done |
| R06 | Reduce synchronous Explorer refresh work | Done |
| R07 | Make artwork caching atomic, retryable and bounded | Done |
| R08 | Isolate activity failures and avoid repeated full rebuilds | Done |
| R09 | Stream folder traversal and expose progress sooner | Done |
| R10 | Remember completed empty metadata fetches | Done |
| R11 | Automate reproducible checks and validate dependency changes | Open; see [Platform and maintenance](#platform-and-maintenance) |
| R12 | Reconcile historical roadmap status with current code | Done |
| R13 | Make migrations atomic and recoverable; provide verified backups | Done |
| R14 | Reconcile credential-vault changes with database commits | Done |
| R15 | Record last-played time only after successful process creation | Done |
