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
  `gui/image_loader.py`) and a Follow button.
- Explorer actions column (Play/Follow/+) rewritten from real per-row
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
- **Next up:** consider restoring PySide6 to latest (currently pinned to
  6.10.1) now that the crash is confirmed fixed independent of version.

## MVP

- Core (project scaffolding, layered architecture wiring)
- Database (SQLite schema per `Database.md`)
- API (RetroAchievements client: auth, games, achievements, median time to
  beat — per `API.md`)
- Settings (API Key, Username, Accounts, ROM folders)
- Explorer (search + filters, Game Cards, Installed status)
- Profile (stats, badges, event awards, recent activity)
- Library (manual ROM matching/organization, no auto-scan yet)
- Lists (Want to Play, Playing, Completed, Abandoned, Following)
- Dashboard (Continue Playing, Recent activity; Recommendations shown as an
  empty placeholder until the v1.1 engine lands — see Version 1.1)
- Search
- Filters

## Version 1.1

- Recommendations engine (history, genres, completion, console preference,
  median time to beat)
- Notifications (achievements released, new supported games, badges,
  events, followed games — opt-in, no spam)
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
