# TrophyTracker — Database

## 1. Principles

- **SQLite**, single local file per install (or per account — see 3.1).
- Local cache: everything the Explorer/Dashboard/Profile need to render must
  be servable from this database with **no network call**.
- Offline-friendly: the app must be usable (browsing cached data) with no
  internet connection.
- Fast startup (< 2s): no heavy queries or full re-syncs on launch.
- API requests only happen to fill cache misses or on explicit
  refresh/background sync — never to satisfy a read in the UI.

> This document defines the **logical schema**. Claude Code should translate
> this into actual `CREATE TABLE` statements / migrations inside
> `src/retrocheevos/database/`, respecting the Architecture doc (Database
> layer only handles persistence, not business rules).

## 2. Core Tables

### 2.1 `accounts`

Stores multiple RetroAchievements accounts supported by the app.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| username | TEXT | RetroAchievements username |
| api_key | TEXT | stored securely, not logged |
| is_active | BOOLEAN | currently selected account |
| last_synced_at | DATETIME | |

### 2.2 `consoles`

Reference table of supported consoles (from RetroAchievements).

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | RetroAchievements console ID |
| name | TEXT | |
| icon_path | TEXT | cached locally |

### 2.3 `games`

Cached game metadata. Games without an achievement set are never synced or
stored here at all — `services/sync_service.py` filters them out server-side
at sync time, and `database/repositories/game_repository.py` unconditionally
excludes `has_achievements = 0` as a defensive floor. Every row in this
table always has `has_achievements = true`.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | RetroAchievements game ID |
| title | TEXT | |
| console_id | INTEGER FK → consoles.id | |
| image_path | TEXT | cached locally |
| genre | TEXT | nullable, future use |
| game_type | TEXT | Retail / Homebrew / Hack / Demo / Prototype |
| has_achievements | BOOLEAN | always `true` (see above) |
| median_time_to_beat_hardcore_seconds | INTEGER | nullable, hardcore-only median time to beat (RA's own field is a median, never call it "average") |
| times_used_in_hardcore_beat_median | INTEGER | nullable, sample size behind the median |
| retroachievements_url | TEXT | e.g. `https://retroachievements.org/game/4909` |
| last_synced_at | DATETIME | drives cache-refresh decisions |

### 2.4 `game_hashes`

ROM hash ↔ game mapping, used for compatibility matching. Never assume
compatibility without an entry here.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| game_id | INTEGER FK → games.id | |
| hash | TEXT | RetroAchievements-supported hash |

### 2.5 `achievements`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | RetroAchievements achievement ID |
| game_id | INTEGER FK → games.id | |
| title | TEXT | |
| description | TEXT | |
| points | INTEGER | |
| badge_path | TEXT | cached locally |

### 2.6 `user_achievements`

Per-account unlock state (hardcore vs. softcore).

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER FK → accounts.id | |
| achievement_id | INTEGER FK → achievements.id | |
| unlocked_at | DATETIME | nullable |
| hardcore | BOOLEAN | |

## 3. Library / Installed Status

### 3.1 `rom_folders`

Watch Folder configuration.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| path | TEXT | |
| console_id | INTEGER FK → consoles.id | nullable if auto-detected |
| watch_enabled | BOOLEAN | |

### 3.2 `installed_roms`

Result of scanning + hashing, links a local file to a `games` row.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| game_id | INTEGER FK → games.id | nullable if unmatched |
| file_path | TEXT | |
| hash | TEXT | matched against `game_hashes.hash` |
| console_id | INTEGER FK → consoles.id | |
| detected_at | DATETIME | |
| last_played_at | DATETIME | nullable; stamped on successful launch |
| file_size | INTEGER | nullable; size in bytes at hash time (R04 fingerprint) |
| file_mtime_ns | INTEGER | nullable; mtime in ns at hash time (R04 fingerprint) |
| manual_match | BOOLEAN | 1 if `game_id` came from "Match to Game…" (R04) |
| account_id | INTEGER FK → accounts.id | nullable for unowned rows (v21) |

`games.installed` status is derived (JOIN against `installed_roms`), not
stored redundantly, to avoid sync drift.

### 3.3 `download_sources` (Future — v1.2+)

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| console_id | INTEGER FK → consoles.id | one source per console |
| source_url | TEXT | |
| install_folder | TEXT | |

### 3.4 `emulator_configs`

Added post-MVP-planning (migration v4) — one configured emulator per
console, powering the "Play" button on the Game Card and Library page.

| Column | Type | Notes |
|---|---|---|
| console_id | INTEGER PK, FK → consoles.id | one emulator per console |
| executable_path | TEXT | path to the emulator executable |
| arguments_template | TEXT | nullable; optional `{rom_path}` placeholder — see Architecture.md's `library/` notes |

### 3.5 `rom_destinations`

Added post-MVP-planning (migration v5) — one user-chosen destination folder
per console, powering Watch Folder organizing (distinct from
`emulator_configs`: that's the emulator executable, this is where ROMs for
that console should be moved to).

| Column | Type | Notes |
|---|---|---|
| console_id | INTEGER PK, FK → consoles.id | one destination per console |
| path | TEXT | folder chosen by the user in Settings > ROM Destinations |

## 4. Lists

### 4.1 `user_lists`

Single table for all list types (Want to Play, Playing, Completed,
Abandoned) rather than "favorites".

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER FK → accounts.id | |
| game_id | INTEGER FK → games.id | |
| list_type | TEXT | enum: `want_to_play`, `playing`, `completed`, `abandoned`, `blocked` |
| added_at | DATETIME | |

Rules enforced at Core layer (not DB constraints):

- `abandoned` and `completed` entries are excluded from default Explorer
  results.
- `blocked` entries are excluded everywhere — Explorer (no opt-in reveal
  filter, unlike `abandoned`/`completed`), Dashboard's Continue Playing,
  and every other list's view (a blocked game disappears from lists it was
  already in too). The only way to see or reverse a block is Settings'
  dedicated Blocked Games list (`remove_from_list`, same as any other list
  membership — blocking isn't a distinct mechanism, just another
  `list_type`).

## 5. Notifications

### 5.1 `notifications`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER FK → accounts.id | |
| type | TEXT | enum: `achievement_released`, `new_supported_game`, `badge`, `event`, `followed_game_update` |
| game_id | INTEGER FK → games.id | nullable |
| message | TEXT | |
| created_at | DATETIME | |
| read | BOOLEAN | |

### 5.2 `notification_settings`

Per-account opt-in/out per notification type (no spam by default beyond
what the user enabled).

| Column | Type | Notes |
|---|---|---|
| account_id | INTEGER FK → accounts.id | |
| type | TEXT | matches `notifications.type` |
| enabled | BOOLEAN | |

## 6. Profile, Badges, Leaderboards (Cache Tables)

### 6.1 `profile_stats`

Snapshot cache of RetroAchievements profile data per account.

| Column | Type | Notes |
|---|---|---|
| account_id | INTEGER FK → accounts.id | PK |
| points | INTEGER | |
| hardcore_points | INTEGER | |
| games_beaten | INTEGER | |
| games_mastered | INTEGER | |
| completion_percentage | REAL | |
| last_synced_at | DATETIME | |

### 6.2 `badges`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER FK → accounts.id | |
| name | TEXT | |
| image_path | TEXT | cached locally |
| owned | BOOLEAN | |
| progress | REAL | nullable, for in-progress badges |

### 6.3 `leaderboard_cache`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| scope | TEXT | enum: `friends`, `daily`, `weekly`, `all_time`, `games_beaten` |
| account_id | INTEGER FK → accounts.id | |
| payload_json | TEXT | cached leaderboard rows |
| last_synced_at | DATETIME | |

### 6.4 `game_completion`

Added post-MVP-planning (migration v3) — per-account, per-game completion
percentage, powering the Explorer Game Card's individual progress bar.
Sourced from `NumAwarded`/`MaxPossible` via `API_GetUserCompletionProgress.php`.
`highest_award_kind` (migration v11) is that same endpoint's per-game award
classification (`HighestAwardKind`) — powers Explorer's unconditional
already-beaten exclusion (`database/repositories/
game_completion_repository.py::get_beaten_game_ids`), mirroring how
`achievements`/`user_achievements` already power already-mastered exclusion.

| Column | Type | Notes |
|---|---|---|
| account_id | INTEGER FK → accounts.id | part of composite PK |
| game_id | INTEGER FK → games.id | part of composite PK |
| percent_complete | REAL | `100 * NumAwarded / MaxPossible`, `0` if `MaxPossible` is 0/unknown |
| highest_award_kind | TEXT | nullable — RA's `HighestAwardKind` (e.g. `beaten-hardcore`, `mastered`), `NULL` if no award yet |
| last_synced_at | DATETIME | |

## 7. Cache Invalidation Rules (Core-layer, not DB-enforced)

| Data | Refresh trigger |
|---|---|
| `games` metadata / median time to beat | Stale after N days, or manual refresh |
| `installed_roms` | On Watch Folder scan event only |
| `user_achievements` | On sync (manual or scheduled) |
| `profile_stats`, `badges`, `leaderboard_cache`, `game_completion` | On sync, throttled to avoid unnecessary API calls |
| `notifications` | Generated by background sync comparing previous vs. new state |

## 8. Indices to Plan For

- `games(console_id)`, `games(has_achievements)`, `games(game_type)` — used
  heavily by Explorer filters.
- `user_lists(account_id, list_type)` — used to exclude Completed/Abandoned
  by default.
- `installed_roms(hash)` and `game_hashes(hash)` — used for fast ROM
  matching during scans.

Exact index definitions belong in the migration files, not this document.
