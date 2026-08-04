# RetroCheevos — UI

## 1. Design Direction

- Inspired by RetroAchievements — **not** a clone.
- Dark mode first.
- Compact.
- Fast.
- Minimal clicks to any action.
- Professional, no clutter.
- Never sacrifice performance for visual effects (no gratuitous animations
  that block or slow the UI thread).

## 2. Navigation

Primary navigation (left sidebar or top nav — implementation detail for
`gui/`), fixed set of destinations:

1. Dashboard
2. Explorer
3. Library
4. Profile
5. Leaderboards
6. Lists
7. Settings

## 3. Screens

### 3.1 Dashboard

Sections:

- Continue Playing
- Recommendations
- Recent activity
- Leaderboards (summary)
- Events
- Recently added achievements

All sections read from local cache; population/refresh handled by
Services/Core in the background.

### 3.2 Explorer (Main Page)

The heart of the app. Contains:

- Search bar (instant, cache-only).
- Filter bar (see 3.2.1).
- Grid/list of Game Cards (see 4.1).
- Recommendations strip.
- Access to user Lists from within results (quick actions on each card).
- Random button (respects active filters).

#### 3.2.1 Filters

- Console (multi-select)
- Genre (future)
- Achievements (has/none)
- Median Time to Beat (togglable on/off)
- Installed
- Completed
- Mastered
- Want to Play
- Playing
- Abandoned
- Following
- Retail
- Homebrew
- Hack
- Demo
- Prototype
- Search with achievements
- Search without achievements
- Search all

Default state: Completed and Mastered games are **hidden** unless the user
enables them via filters.

### 3.3 Library

- Shows the ROM library organized by console (one folder per console,
  mirrored in UI).
- Watch Folder management (add/remove watched folders).
- Installed / Not Installed status per game, driven by the scan results.
- Manual "Scan now" action, runs on a background thread.
- Play an installed game directly in its configured emulator (Settings §3.7
  "Emulators"), launched as an independent background process.

### 3.4 Profile

- RetroAchievements profile summary.
- Player statistics: points, hardcore points, completion percentage, games
  beaten, games mastered.
- Badges (owned/missing) and Event Awards.
- Recent activity feed.

### 3.5 Leaderboards

- Current RetroAchievements leaderboards.
- Friends leaderboard.
- Daily / Weekly / All Time tabs.
- Custom "Games Beaten" leaderboard.

### 3.6 Lists

- Want to Play
- Playing
- Completed
- Abandoned
- Following

Each list is a filtered view over `user_lists`, reusing the Game Card
component from Explorer.

### 3.7 Settings

- API Key
- Username
- Accounts (add/remove/switch)
- ROM folders (Watch Folder configuration)
- Emulators (executable path + optional launch arguments, per console;
  Database.md 3.4)
- Download folders (future)
- Download sources (future)
- Theme
- Language
- Cache (view size / clear cache)

## 4. Components

### 4.1 Explorer Game Card

Displays:

- Game image
- Title
- Console
- Median Time to Beat (Hardcore)
- Hardcore Beat Median Sample Size
- Completion progress bar (per-account `percent_complete`, Database.md 6.4)
- Installed icon (Installed / Not Installed)
- Play button — launches the installed ROM in the console's configured
  emulator (Settings §3.7), as an independent background process
- Quick actions (e.g. add to a list, one click)
- Three-dot menu (see 4.2)

### 4.2 Three-dot Menu (per game)

- Want to Play
- Playing
- Abandoned
- Following
- Open on RetroAchievements (opens `retroachievements_url` externally)

## 5. Interaction Principles

- Minimal clicks: common actions (add to list, open on RetroAchievements)
  must be reachable in one or two clicks from the Game Card, without opening
  a full detail page when not necessary.
- Search and filtering must feel instant — no spinners for cache-only
  operations.
- Any operation touching the network or disk I/O (sync, scan, download)
  must show non-blocking progress feedback (status bar / toast / progress
  indicator) while the UI remains fully responsive.

## 6. Future UI Considerations

- Steam Deck / Linux: only this layer (`gui/`) should need adaptation for
  controller navigation and screen size — business logic stays untouched
  (see `ARCHITECTURE.md` §6).
- Plugin system and Themes (future) should be considered when designing the
  Settings screen and the overall styling layer, even though they are out
  of scope for the MVP.
