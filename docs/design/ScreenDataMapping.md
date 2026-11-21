# Screen, action and data mapping (R16)

Status: first complete pass, 2026-11-20. Inputs: the
[reviewed UI proposal](ui-proposal-reviewed.html), the
[product fit review](ProposalReview.md) and the desktop code at commit
`a78cd13`. This document is the R16 deliverable in the
[roadmap](../planning/DevelopmentRoadmap.md#foundation). It maps what exists
today to the eight reviewed boards. It does not implement anything.

Paths are relative to `src/retrocheevos/`. "Board" means one screen of the
reviewed proposal.

## 1. Findings that change the plan

These came out of the inventory and are not visible from the proposal alone.
Decisions D7–D9 were resolved on 2026-11-20; see §7.

| ID | Finding | Effect |
| --- | --- | --- |
| F1 | **Badges are synced but never shown.** `sync_service.sync_profile` stores awards through `ProfileRepository.upsert_badge`, but no repository method reads them and no widget displays them. The current Home "Events" section lists event *games* with progress (`services/events_service.py`), not awards. Earlier documentation said Home shows badges. | The Home board's "Badges and event awards" entry needs a new read method and a view. This is new work, not a restyle. **D7:** an Awards view reached from Home. |
| F2 | **Progress counts are not per mode.** `GameCompletion.achievements_unlocked/total` come from `NumAwarded`/`MaxPossible` of `API_GetUserCompletionProgress.php`, a single count. `UserAchievement` keeps one `unlocked_at` plus a `hardcore` flag, so a softcore date is lost once the hardcore unlock exists. | "34/42" on Home, Library and Lists cards cannot be labeled hardcore or softcore today. **D8:** cards keep the combined count, labeled "achievements". Game detail needs per-mode data (see §5). |
| F3 | **Achievement definitions are rarely stored.** `AchievementRepository` is filled by `sync_game_details`, which only runs from the ROM hash backfill with full details. Most games have no stored achievement list. | Game and achievement details need an on-demand fetch (§5). Stored data is a cache, not a reliable source. |
| F4 | **"No achievement set" cannot be determined locally.** Games without an achievement set are never stored (`GameRepository` filters `has_achievements = 1`). A local ROM that matches nothing is indistinguishable from one whose game has no set. | Library's "No achievement set" filter cannot be implemented as drawn. **D9:** replaced by **Unmatched** ("no catalog match; progress unavailable"). |
| F5 | **ROM folders have no scan history or link.** `installed_roms` has no `rom_folder_id` and `RomFolder` has no last-scan time. | Per-folder counts can only be derived by path prefix. Settings and Library must not show "last scanned" or "no scan results yet" without a schema change. Showing "N ROMs indexed under this folder" by path prefix is feasible. |
| F6 | **Settings has no appearance, window or update controls.** Window state is saved automatically; the update check is disabled because `version.py` has no release source. | R24's "retain appearance/window/update controls" has nothing to retain. The roadmap text is corrected. |
| F7 | **Catalog sync lives in Explorer.** Sync Everything, Sync Median Times and Sync ROM Hashes are buttons on `ExplorerPage`. The reviewed Explorer board omits them and the Settings board shows "Sync catalog and profile". | Move all three to Settings → Synchronization. The Sync ROM Hashes "with full details" question dialog moves with it. Home's "Sync now" maps to the profile sync only. Sync Everything also feeds Home's new-events banner (`HomePage._on_sync_finished`); that signal must follow the move. |
| F8 | **List rows only offer Remove.** `widgets/list_entry_row.py` emits `remove_requested` only. | Play and Details on the Lists board are new actions. Play reuses `library_service.launch_game`. |
| F9 | **Current Home elements missing from the boards:** Events section with the new-events banner, Beaten Games Leaderboard link, completion percentage, cover size slider, displayed-account line, update banner and version label. | Each needs a place (see §3.1). The leaderboard stays an external link. |
| F10 | **Explorer has no Details or Open on RA action today.** Rows offer Play (when installed) and a "+" menu (add to list, block). `Game.retroachievements_url` already exists. | Details and Open on RA are new row actions. |

## 2. Current action inventory

Every user-reachable action in the current desktop UI, with its target in the
revamp. Status: **kept** (same function, restyled), **moved** (new location),
**new** (does not exist today), **changed** (behavior differs).

### 2.1 Shell and header (`gui/main_window.py`, header from `gui/pages/home_page.py`)

| Action | Implementation | Target | Status |
| --- | --- | --- | --- |
| Navigate Home/Library/Lists/Settings | Sidebar `QPushButton`s → `_show_page` | Sidebar (R18) | kept |
| Open user menu (hover/click avatar) | `HomePage._show_user_menu` | Sidebar account area | moved |
| Menu: navigate to a destination | `USER_MENU_DESTINATIONS` | Removed; sidebar covers it | removed |
| Menu: Displayed account → choose saved account | `account_menu` → `login_requested` | Sidebar account area; Settings | kept |
| Menu: Logout | `logout_requested` → `session_service.logout` | Sidebar account area ("Sign out") | kept |
| Menu: Login as saved account | `login_requested` | Sidebar account area | kept |
| Menu: Add an account | navigates to Settings | Sidebar account area; onboarding (R24) | kept |
| Update banner: open release, dismiss | `widgets/update_banner.py` | Shell, above content | kept (inactive until a release source exists) |
| Version label | `QLabel#versionBadge` | Sidebar footer | moved |

### 2.2 Home (`gui/pages/home_page.py`)

| Action | Implementation | Target | Status |
| --- | --- | --- | --- |
| Search catalog (expands embedded Explorer) | `_search_input`, embedded `ExplorerPage` | Home "Explore catalog" / search → Explorer | kept |
| Back to Home from embedded Explorer | `_back_to_home_button` | Back navigation (R18) | changed |
| Refresh Continue Playing | `_on_refresh_continue_playing` | Home "Sync now" area | moved |
| Cover size slider | `widgets/cover_size_slider.py` | Removed from Home; card size fixed by layout | **decision in R19** |
| Play from Continue Playing (matched/unmatched) | `library_service.launch_game` / `launch_installed_rom` | Continue Playing card | kept |
| Now Playing: refresh progress | `widgets/now_playing_panel.py` | Home Now Playing panel | kept |
| Events: open event on RA | `widgets/event_row.py` → `openUrl` | Awards view (D7) | moved |
| New events banner: mark read | `_on_new_events_banner_clicked` → `notification_service.mark_events_read` | Same view | moved |
| Beaten Games Leaderboard (external) | `openUrl(BEATEN_GAMES_LEADERBOARD_URL)` | Link from the Beaten games metric | moved |
| Recent Activity (passive, auto refresh with backoff) | `activity_feed_service` | Home Recent Activity | kept |

### 2.3 Explorer (`gui/pages/explorer_page.py`, `widgets/explorer_filter_bar.py`, `gui/delegates/explorer_delegates.py`)

| Action | Implementation | Target | Status |
| --- | --- | --- | --- |
| Search | `_search_input`, debounced snapshot worker | Explorer search | kept |
| Filter: consoles, game types, median time (apply/clear), installed, lists, reset | `ExplorerFilterBar` | Explorer chips | kept |
| Sort by column | `ExplorerTableModel` | Explorer table | kept |
| Play (installed games) | `ActionsDelegate` | Row action | kept |
| Add to list / Block | "+" menu in `ActionsDelegate` | Row "List" menu; Block in same menu | kept |
| Details | — | Row action → game detail (R21) | new |
| Open on RA | — | Row action, `Game.retroachievements_url` | new |
| Sync Everything | `_on_sync_everything` → `sync_service.sync_everything` | Settings → Synchronization ("Sync catalog and profile") | moved (F7) |
| Sync Median Times | `_on_sync_median_times` | Settings → Synchronization | moved (F7) |
| Sync ROM Hashes (+ "with full details?" question) | `_on_sync_game_hashes` | Settings → Synchronization | moved (F7) |

### 2.4 Library (`gui/pages/library_page.py`)

| Action | Implementation | Target | Status |
| --- | --- | --- | --- |
| Refresh | `refresh` | Implicit on show; scan button | removed as a separate button |
| Cover size slider | `CoverSizeSlider` | Adaptive grid (R22) | **decision in R22** |
| Add folder for console | `QFileDialog.getExistingDirectory` → `add_rom_folder` | Shared folder editor (Library and Settings) | kept |
| Remove selected folder | `remove_rom_folder` | Shared folder editor | kept |
| Scan selected folder | `scan_rom_folder` (cancellable, progress) | Library "Scan folder" | kept |
| Scan all folders | `scan_all_rom_folders` | Library scan menu | kept |
| Re-hash (forced verification) | `rehash_installed_roms` | Library scan menu | kept |
| Match unmatched ROM to game | `MatchRomDialog` → `match_installed_rom_to_game` | Unmatched card "Match to game…" | kept |
| Scan a single ROM file | `QFileDialog.getOpenFileName` → `scan_and_record_rom` | Library scan menu | kept |
| Remove unmatched ROM record | `remove_installed_rom` | Unmatched card menu | kept |
| Remove matched game from library | `InstalledGameFrame` context menu → `remove_installed_roms_for_game` | Card context menu | kept |
| Pick custom cover (unmatched) | `UnmatchedRomCard` → `QFileDialog` | Card context menu | kept |
| Play (matched/unmatched) | `launch_game` / `launch_installed_rom` | Card Play | kept |
| Local search, status filters, system filter | — | Library toolbar | new |
| Configure emulator (from card) | — | Opens shared emulator editor | new |
| Details | — | Card → game detail | new |

### 2.5 Lists (`gui/pages/lists_page.py`)

| Action | Implementation | Target | Status |
| --- | --- | --- | --- |
| Select list | `QComboBox` | List column | kept |
| New list | `QInputDialog` → `lists_service.create_list` | "New list" | kept |
| Rename list (not Blocked) | `QInputDialog` → `rename_list` | "Rename list" | kept |
| Delete list (not Blocked, confirmation) | `QMessageBox.question` → `delete_list` | "Delete list…" | kept |
| Remove from list / Unblock | `ListEntryRow.remove_requested` | Row action | kept |
| Play, Details | — | Row actions | new (F8) |
| Explore catalog (empty state) | — | Empty state link | new |

### 2.6 Settings (`gui/pages/settings_page.py`)

| Action | Implementation | Target | Status |
| --- | --- | --- | --- |
| Save account (username, API key) | `session_service.add_account` | RetroAchievements account | kept |
| Display selected account | `switch_account` | Displayed account | kept |
| Remove account (confirmation with data counts) | `count_account_data` → `remove_account` | Account list | kept |
| Sign out | — (only in the user menu today) | RetroAchievements account | moved |
| Emulator: console, path, browse, find, arguments, core, save | `library_service.set_emulator_config`, `FindEmulatorDialog` | Emulator configuration → edit dialog | kept |
| Remove emulator config | `remove_emulator_config` | Emulator row | kept |
| Sync profile | `sync_service.sync_profile` | Synchronization | kept |
| ROM folders | — (Library only today) | ROM folders section, shared editor | new entry point |
| Catalog syncs | Explorer today | Synchronization | moved (F7) |

### 2.7 Dialogs

| Dialog | Trigger | Target |
| --- | --- | --- |
| `MatchRomDialog` (search games of the ROM's console) | Library | Kept; restyle (R27 secondary dialogs) |
| `FindEmulatorDialog` (installed apps, common locations, folder search, cancellable) | Settings emulator editor | Kept; restyle |
| `QFileDialog`: ROM folder, ROM file, emulator, core, cover image | Library, Settings, unmatched card | Native dialogs, unchanged |
| `QInputDialog`: list name (new/rename) | Lists | Replace with an inline name field or small styled dialog |
| Confirm: delete list | Lists | Kept; text states ROM files are not deleted |
| Confirm: remove account (with data counts) | Settings | Kept |
| Question: hash sync with full details | Settings (after F7) | Kept |
| Warnings: busy job, launch failure, scan/rehash failure, missing info, invalid image | Various | Inline banner where non-blocking (R25); keep a dialog only where a decision is needed |
| Info: hashes synced, median times synced | Settings (after F7) | Inline result in the Synchronization section |

## 3. Board mapping

Each element of a board, its data source, and what to show when the data is
missing or fails. "Freshness" names the timestamp shown to the user.

### 3.1 Home

| Element | Source | Missing / failure state |
| --- | --- | --- |
| Last synced · Sync now | `ProfileStats.last_synced_at`; `sync_service.sync_profile` | "Never synced" with Sync now; busy job → disabled with the job name |
| Points, True points | `ProfileStats.points`, `true_points` | "—" with "not synced yet" |
| Beaten games, Mastered games | `ProfileStats.games_beaten`, `games_mastered` | "—"; Beaten links to the external leaderboard (F9) |
| Explore catalog, Your lists | Navigation | — |
| Continue Playing (cover, console, X/Y, Play) | `dashboard_service.get_continue_playing_games`, `get_unmatched_continue_playing_roms`; counts from `GameCompletion` (F2) | Empty: "Play a game from Library to see it here"; unknown counts shown as "progress unavailable" |
| Recent Activity (followed users) | `activity_feed_service.get_recent_activity_feed` (live, in-memory only) | Loading; partial ("N users unavailable"); failed with last good entries kept for the session; following unavailable |
| Now Playing | `now_playing_service.refresh_now_playing`; freshness `NowPlayingSnapshot.checked_at` | "No recent game activity reported"; unmatched ROM notice |
| Badges and event awards → Awards view (D7) | Badges: new `ProfileRepository` read method (F1); events from `events_service.list_events_with_progress`; unread from `notification_service` | No badges synced → "Sync profile to load awards"; no events → Events section hidden |
| Completion percentage, displayed account | `ProfileStats.completion_percentage`; active account | Account shown in the sidebar instead; completion % moves to a metric tooltip or is dropped (R19) |

### 3.2 Library

| Element | Source | Missing / failure state |
| --- | --- | --- |
| "N local ROMs indexed" | `library_service.list_installed_roms()` count | "No ROMs indexed yet" + Add folder |
| Scan folder (menu: selected, all, single file, forced verification) | `scan_rom_folder`, `scan_all_rom_folders`, `scan_and_record_rom`, `rehash_installed_roms` | Progress with discovered count; cancellation; result summary of ambiguous, unrecognized, failed and changed paths |
| Local search | New filter over installed games and unmatched ROMs (title, file name) | "No local games match" |
| Filter All | All installed games + unmatched ROMs | — |
| Filter In progress | `GameCompletion.percent_complete` > 0 and not mastered | Games with no completion record are excluded, not shown as 0% |
| Filter Mastered | `AchievementRepository.get_mastered_game_ids` / `highest_award_kind` | — |
| Filter Unmatched (replaces No achievement set, D9) | Installed ROMs with no `game_id` | "All local ROMs are matched" |
| System filter | `InstalledRom.console_id` → `console_service.list_consoles` | — |
| Card: cover, title, console, X/Y | `image_service.ensure_game_image_cached` / `ensure_rom_image_cached`; `GameCompletion` | Fallback cover; "progress unavailable" when no completion record |
| Card Play | `launch_game` / `launch_installed_rom` | No emulator for console → "Configure emulator"; missing file → "File not found" with Remove |
| Unmatched card: Match to game…, Configure emulator | `MatchRomDialog`; emulator editor | Ambiguous matches listed from the scan result |

### 3.3 Game detail (new destination, R21)

| Element | Source | Missing / failure state |
| --- | --- | --- |
| Back ("‹ Library") | Navigation history with origin state | — |
| Cover, title, console | `Game`, `image_service` | Fallback cover |
| X/Y achievements, earned/total points | Game detail contract (§5), per mode | Loading; offline with cached data; "achievement list not available offline" when never fetched |
| Play, emulator name, ROM path | `library_service` installed ROM + `EmulatorConfig` | Not installed → no Play, "Not in your library"; no emulator → "Configure emulator" |
| Account, Mode | Active account; mode selector Hardcore/Softcore | — |
| Add to list…, Open on RA | `lists_service`, `Game.retroachievements_url` | — |
| All / Unlocked / Missing filters, Sort: Points | Contract §5, per selected mode | "No achievements match" |
| Achievement rows (title, description, points, state) | Contract §5 | Badge fallback icon |

### 3.4 Achievement detail (new destination, R21)

| Element | Source | Missing / failure state |
| --- | --- | --- |
| Back ("‹ Game · Achievements") | Navigation history | — |
| State, title, description, points | Contract §5 | — |
| Hardcore / softcore state and unlock date | Contract §5 | "No unlock date recorded" when unknown |
| Play game | Same rules as game detail | — |
| Open on RA / community | `https://retroachievements.org/achievement/{id}` | — |
| Last synced · Refresh progress | Contract §5 `fetched_at` | Offline: cached state with its date |

### 3.5 Settings

| Element | Source | Missing / failure state |
| --- | --- | --- |
| Account form, saved accounts, Display selected account, Sign out, Remove | `session_service` | Vault unavailable → note that the key is stored in the database fallback |
| Synchronization: Sync profile; Sync catalog and profile; Median times; ROM hashes | `sync_service` (F7) | One job at a time via `job_coordinator`; progress and cancellation; inline result |
| ROM folders: list, Add, Scan, Remove | `library_service` folder functions; per-folder ROM count by path prefix (F5) | No last-scan time shown |
| Emulator configuration table (system, emulator/core, Edit) | `list_emulator_configs`; console names | "No emulators configured" + Configure emulator |
| "Example files" column (extensions) | `library/console_catalog.py` extension tables | Omit the column if extensions for a console are not single-valued |

### 3.6 Explorer

| Element | Source | Missing / failure state |
| --- | --- | --- |
| Search, filters, reset | `explorer_service.get_snapshot`, `ExplorerFilterBar` | "No catalog games match"; catalog never synced → "Sync catalog in Settings" |
| Columns: game, system, median beat time, progress | `ExplorerTableModel` | Median "Unknown"; progress "Not synced" |
| Row actions: Play, Details, List, Block, Open on RA | `ActionsDelegate` + new actions (F10) | Play only when installed |
| Note on exclusions | `core/explorer.py` rules | — |

### 3.7 Lists

| Element | Source | Missing / failure state |
| --- | --- | --- |
| List column with counts | `lists_service.list_definitions`, `get_games_in_list` | No custom lists → only Blocked + New list |
| New, Rename, Delete | `lists_service` | Blocked: rename and delete disabled |
| Rows: cover, title, console, X/Y, Play, Details, Remove | `get_games_in_list`, `GameCompletion`, launch functions | Not installed → no Play |
| Empty list state | — | "Add games from the catalog, Library or game details" + Explore catalog |

### 3.8 Brand

Covered by R17; no runtime data. Assets in `assets/`, history in
[Branding.md](Branding.md).

## 4. Scopes, freshness and states

**Account scope.** Every board shows the explicitly displayed account
(`session_service.get_active_account`). Library ROMs, folders and lists are
account-scoped (migration v21); the catalog (`games`, consoles) and emulator
configuration are shared. Worker results carry the account ID and generation
and are discarded after a switch (R01).

**Mode scope.**

- Profile metrics (points, hardcore points, true points, beaten, mastered)
  are account-wide figures reported by RetroAchievements.
- Card counts (Home, Library, Lists, Explorer progress) are RetroAchievements'
  combined `NumAwarded`/`MaxPossible` (D8); label them "achievements",
  never "hardcore".
- Game and achievement details are always per mode. Never add hardcore and
  softcore counts together.

**Freshness sources.**

| Data | Timestamp |
| --- | --- |
| Profile metrics, completion records | `ProfileStats.last_synced_at`, `GameCompletion.last_synced_at` |
| Catalog games | `Game.last_synced_at` |
| Now Playing | `NowPlayingSnapshot.checked_at` |
| Recent Activity | Time of the last successful fetch in this session (not persisted) |
| Game detail | `fetched_at` from §5 |

**Unknown is not zero.** No completion record → "progress unavailable". No
median time → "Unknown". No unlock date → "No unlock date recorded". An
unmatched ROM → "no catalog match", not "no achievements".

**State checklist per board** (input to R25): initial loading, cached
refresh, empty, no account, offline, partial success, retryable error, busy
job (another sync running), destructive confirmation.

## 5. Game detail data contract (input to R21)

A new service, proposed as `services/game_detail_service.py`:

```python
def get_game_detail(account: Account, game_id: int,
                    should_cancel=None) -> GameDetail: ...
```

- **One request:** `API_GetGameInfoAndUserProgress.php` (`u`, `g`), already
  parsed by `AchievementProgressClient.get_live_game_progress`. It returns the
  core achievement definitions and the account's softcore and hardcore unlock
  dates in one call.
- **Result** (`GameDetail`): game ID and title; console; achievements (ID,
  title, description, points, badge, `unlocked_softcore_at`,
  `unlocked_hardcore_at`); per mode: unlocked count, total, earned points and
  total points; `fetched_at`; `source` = `live` or `cache`.
- **Persistence:** upsert definitions into `achievements` and unlocks into
  `user_achievements` in one transaction, so later opens work offline. Keeping
  both dates needs a schema change, because `UserAchievement` stores one date
  (F2). Until then, the cached view can show hardcore unlocked or unlocked
  (softcore) correctly, but loses the softcore date once a hardcore date
  exists.
- **Cache policy:** show cached data immediately if present, then refresh if
  older than a threshold (proposed: 10 minutes) or on Refresh progress. Use the
  shared API pacing (R03); no request when offline and cache exists.
- **Errors:** authentication error → account state message; rate limit →
  backoff and keep cached data; game without stored definitions while offline
  → "achievement list not available offline".
- **Badge images:** fetched through `image_service` within the R07 budget,
  only for visible rows.
- **To verify against the live API before implementation:** per-achievement
  fields not parsed today (for example award counts) and whether
  `API_GetUserCompletionProgress.php` also reports a hardcore count, which
  would allow per-mode card counts (D8). Neither is used until verified.

## 6. Small windows

Reference 1240×780; minimum 1024×720 (R18). Proposed behavior below the
reference width:

| Area | Below ~1180 px window width |
| --- | --- |
| Sidebar | Stays 220 px down to 1100 px; below that, a 72 px icon rail with tooltips and the account avatar |
| Home | Metrics stay in one row of four, shrinking text; Continue Playing and Recent Activity stack vertically below ~1100 px; Now Playing and awards follow |
| Library | Grid columns from available width with a minimum card width (proposed 200 px): 4 → 3 → 2 |
| Game detail | Header wraps: cover and title above, actions below; list unchanged |
| Achievement detail | Side panels move under the main card |
| Settings | Single column; emulator table keeps System and Edit columns, wraps the rest |
| Explorer | Title column elides; median time column is the first to hide; actions remain visible |
| Lists | List column collapses to a selector above the rows |

All actions stay reachable at 1024×720 and at 150% scaling (validated in R26).

## 7. Decisions

Resolved on 2026-11-20 and recorded in the roadmap's resolved decisions:

- **D7:** badges and event awards are shown in an Awards view reached from
  Home, combining badges with the current Events list (F1).
- **D8:** cards keep RetroAchievements' combined count, labeled
  "achievements"; details are per mode. Per-mode card counts are revisited only
  if R21 confirms a hardcore count from the API (F2).
- **D9:** Library's "No achievement set" filter becomes Unmatched (F4).

Smaller choices resolved inside the owning item: cover size sliders (R19,
R22), completion percentage on Home (R19), inline versus dialog list naming
(R23).
