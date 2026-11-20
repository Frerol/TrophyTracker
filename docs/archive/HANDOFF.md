> Historical implementation handoff. Descriptions and examples may refer to
> earlier application behavior. Use the [current roadmap](../planning/DevelopmentRoadmap.md)
> and [documentation index](../README.md) for active work and file locations.

# TrophyTracker — Session handoff

Project state for resuming in a new session without prior context.
Last updated: end of Block 10. Later implementation notes follow below.

---

## 0. Quick context for a new contributor

A desktop app (Python 3.14 + PySide6) tracking a RetroAchievements account:
searchable catalog, locally installed games, progress, events, and emulator launching.

- **Run:** `.venv/Scripts/python.exe -m retrocheevos.main` (or `src/retrocheevos/main.py`).
- **Database:** `database/retrocheevos.db` (SQLite), migrations in `src/retrocheevos/database/migrations.py` — **version at this point: 14**.
- **Layers:** `gui/` → `services/` → `core/` → `database/` + `api/`. The GUI never calls `api/` directly.
- **Tests at this point:** only `tests/library/`; **pytest was not installed in the venv**. Verification used `py_compile`, importing the entire app, and targeted scripts against the real database and live API.
- **Historical note:** at the time of writing, parts of UI.md, Architecture.md, Database.md, and DevelopmentRoadmap.md were outdated, and this handoff was the latest account. The current roadmap now takes precedence.

---

## 1. Current milestone: Block 10 (complete)

Work was organized into numbered blocks. Blocks 1–9 and **Block 10** (UI fixes and adjustments) were complete.

### Implemented and verified in Block 10

| # | Item | Status |
|---|---|---|
| 1 | Sync bar always visible, including during search | Complete |
| 2 | Six-column Continue Playing grid and wider sidebar | Complete |
| 3 | Badges section removed from Home | Complete |
| 4+8 | Console dropdown removed; global `sync_median_times` | Complete |
| 5 | App icon with seven pre-scaled resolutions, 16–256 px | See §4 |
| 6 | Progress bars on a fixed 0–100 scale with percentages | Complete |
| 7 | Mutually exclusive All option in the Type filter | Complete |
| 9 | Beaten Games Leaderboard button opens the browser | Complete |

### Second round of Block 10 fixes

| # | Item | Status |
|---|---|---|
| 1 | Incorrect widths flattened the sidebar | Fixed: `setMaximumWidth` without `setMinimumWidth` |
| 2 | Sixth Continue Playing game missing | Diablo was at 100% and excluded by a rule |
| 3 | Leaderboards button outside navigation | Page deleted |
| 4 | Duration displayed as 1.5h (n=33) | Changed to 1h 30m |
| 5 | Download button still visible | Signal, handler, and painting removed |
| 6 | Continue Playing lacked a visual progress bar | `QProgressBar` restored |
| 7 | Statistics differed from the website | See §2 |

---

## 2. Remaining work — an evidence-based account

> The request behind this handoff listed three unresolved issues. Two were
> already resolved and confirmed; the third encountered an external limit.
> The evidence below records the investigation so later sessions do not repeat it.

### 2.1 Statistics (Beaten/Mastered/Completion) — resolved and confirmed

The initial causes and the reason the fix was not visible were:

1. **Only the first API page was read.** `API_GetUserCompletionProgress.php`
   returns at most 100 games and reports the actual count in `Total` (live
   check: 100 returned, `Total = 147`). Statistics therefore covered only
   about two-thirds of the account. `api/profile.py::get_user_completion_progress`
   was changed to follow pagination.
2. **Mastered games did not count as beaten.** `highest_award_kind` stores
   only the highest award, so the 46 mastered games were excluded from the
   beaten total. `BEATEN_AWARD_KINDS` now includes `completed` and `mastered`.
3. **The corrected formula did not reach the screen.** `profile_stats` was
   validated only by age (`PROFILE_SYNC_STALE_AFTER = 6h`). Its row was only
   22 minutes old, so synchronization was skipped. Age cannot detect a
   formula change. Migration v14 added `profile_stats.stats_revision`,
   compared with `sync_service.PROFILE_STATS_REVISION` (then `1`). A revision
   mismatch forces synchronization regardless of age.

Database evidence after the first fix:

```text
stored stats: beaten=98 mastered=56 completion=42.21 revision=1
```

Previously: 28 / 46 / 63.12%, revision 0.

#### Completion percentage — resolved, exact website match (2026-08-06)

The website displayed Average completion = **56.75%**. Neither earlier
formula matched, and the errors worked in opposite directions:

| Formula | Value |
|---|---|
| Unweighted average, first page only (original) | 63.12% |
| `sum(earned) / sum(available)`, weighted, revision 1 | 42.21% |
| Unweighted average, all 147 games | 56.37% |
| **Unweighted average, all games except subsets** | **56.75%** |

The unweighted formula was correct originally; missing pagination inflated
it. Replacing it with a weighted ratio introduced a larger error. The final
0.38 percentage-point difference came from one row:
`Dragon Ball Z: Budokai [Subset - Martial Arts Tournament]`, at 1.43%.
Excluding it gives 56.7470 → **56.75%**, consistent with the subset exclusions
already used by `_BROWSABLE_GAME_CLAUSES`.

Verified through the actual code path:

```text
games_beaten          : 98      (website: 98)
games_mastered        : 56      (website: 56)
completion_percentage : 56.7470 (website: 56.75%)
```

**`PROFILE_STATS_REVISION` increased to 2** so the corrected result would reach the UI.

Two questions could not be distinguished using this account: it had no
softcore points, making `NumAwarded` and `NumAwardedHardcore` identical; and
it had no event/standalone games (consoles 101/102), so their exclusion could
not be tested. Only the proven subset exclusion was applied.

### 2.2 Recent Activity — resolved and closed

The first investigation found no malfunction: the `QTimer` starts in
`showEvent` and stops in `hideEvent`, confirmed headlessly with
`QStackedWidget`. A live fetch took about 5.7 seconds, well within the interval.

Improvements applied anyway:

- Refresh interval reduced from 60 to **30 seconds**.
- **Immediate** refresh when showing the page, rather than waiting a whole interval after returning to the window without navigation.
- **Actual bug fixed:** refreshing during an ongoing fetch cleared `_activity_entries` without starting a new worker. It now returns before modifying state.

#### Second investigation — the data itself (2026-08-06)

The user reported that Theodoro's entry showed `2026-08-06 00:45`, 74/88,
after previously showing `2026-08-06 10:53`, 75/88: older activity with less
progress. Three suspected causes were checked live:

| Suspect | Measured result |
|---|---|
| Ordering | `API_GetUserRecentAchievements.php` returned strictly descending timestamps: 84 rows, `dates == sorted(dates, reverse=True)` |
| Pagination | None: `m=10080` returned all 84 rows in the window, newest at index 0 |
| Cache | Two consecutive `API_GetGameInfoAndUserProgress.php` calls returned identical values; `requests.Session` does not cache and the service persisted nothing |

**The API agreed with the UI.** Theodoro's latest unlock was
`2026-08-06 00:45:40` in Jak 3, with `NumAwardedToUser = 74` of 88. No 10:53
unlock or 75/88 result existed in the returned data. The only other game in
the seven-day window was Metal Gear Solid: Ghost Babel at 13/106, ruling out
a game mix-up.

**Most likely explanation for the earlier 75/88:** RetroAchievements revoked
or reset an unlock. A return from 75 to 74, with the 10:53 unlock disappearing,
is internally consistent and cannot be detected from the remaining API data.
The app could have been correct on both occasions.

#### Actual bug found in that round: time zones

`API_GetUserRecentAchievements.php` returns `Date` in **UTC**, without an
offset. Cross-check: the award `2026-08-05T10:11:40+00:00` for game 757 from
`API_GetUserAwards.php` is the same event reported as `2026-08-05 10:11:40`.
`ActivityEntryCard` displayed the raw value, one hour behind the local UTC+1
clock, which looked like stale data.

> The `_as_utc()` / `_format_local()` changes described here were later
> reverted at the user's request; raw UTC is displayed. The evidence that
> the timestamps are UTC still stands.

Changes made in that round, partly reverted later:

- `api/profile.py`: `_as_utc()` marked naive timestamps as UTC.
- `widgets/activity_entry_card.py`: `_format_local()` converted them to the machine's time zone.
- `services/activity_feed_service.py`: `_latest_unlock()` selected by timestamp rather than index `[0]`. The observed API ordering was correct but undocumented; relying on position could produce the reported symptom.

#### Fourth round — center the card on the game rather than the unlock

The user requested removing Last unlock and placing the last/current game
below Last seen. This changed the data source as well as the order:

- The game formerly came from `API_GetUserRecentAchievements.php`, meaning
  the game of the **last unlock**. It now comes from `LastGame` in
  `API_GetUserSummary.php`, the game the person was actually playing. A
  session can last hours without an unlock.
- This removed the feed's `get_recent_achievements` call, `last_achievement_at`,
  and `_latest_unlock`: **three calls became two per user**. With about 31
  users and 0.3-second pacing, this cuts refresh time by roughly one-third.
- `RawUserSummary` gained `last_game_title`, `last_game_console`, and
  `last_game_icon_path`. `core/activity_feed.py` already sorted by
  `last_seen_at`; the unlock fallback was removed.

Card order: user → Last seen → game (icon, title, console) → progress → rich
presence. Verified with the real summary payload:

```text
Theodoro
    Last seen: 2026-08-06 18:09
    Jak 3 — PlayStation 2
    75/88 achievements | Played 19h31m
    Story Missions: 60/60 | Orbs: 449
```

#### The + menu marks lists that already contain the game

`ActionsDelegate.set_membership_provider(fn)` receives
`fn(game_id) -> set[list_id]` from `ExplorerPage`. It uses a callback rather
than a pushed dictionary: calculating membership for thousands of table
rows to answer one lazily constructed menu would waste work. Membership is
queried only when the menu opens.

Unchecked entries receive a figure space (` `) to align them with checked
entries. Qt checkable actions were intentionally avoided: clicking adds to
a list, while a checkbox would imply toggling membership off as well.

#### Third round — the actual cause: Last seen differs from last unlock

The user's side-by-side comparison showed `Last seen 06 Aug 2026, 17:21` on
the website and `Last activity: 2026-08-06 01:45` in the app: a 16-hour gap.
The app displayed the last **unlock**; the website displayed the last time
**playing**. Theodoro had been playing for hours without unlocking anything.

`API_GetUserProfile.php` has no last-seen field, which explains the earlier
unlock-based fallback. `API_GetUserSummary.php` provides:

```text
RichPresenceMsgDate          = 2026-08-06 17:31:50   <- use this
RecentlyPlayed[0].LastPlayed = 2026-08-06 17:31:50   <- agrees
LastActivity.lastupdate      = None                  <- dead end
```

Every key in `LastActivity` was null. `RichPresenceMsgDate` is a scalar and
avoids indexing a list that is empty for users who have never played.

Changes:

- `api/profile.py`: `get_user_summary()` and `RawUserSummary`.
- `models/activity_feed.py`: `last_seen_at` alongside `last_achievement_at`.
- `services/activity_feed_service.py`: summary instead of profile; still three calls per user at that stage.
- `core/activity_feed.py`: sort by `last_seen_at`, like the Following page.
- `widgets/activity_entry_card.py`: separate Last seen and Last unlock lines.

Verified end to end against the live API:

```text
Theodoro   seen=2026-08-06 18:36  unlock=2026-08-06 18:36  75/88  Jak 3
Gmendes    seen=2026-08-06 08:23  unlock=2026-08-05 11:11  1/31   DBZ: Taiketsu
Zynlar     seen=2026-07-30 02:14  unlock=-
```

Gmendes's row demonstrates the difference between the two clocks.

#### Time-zone decision: display raw UTC without conversion

**Final user decision (2026-08-06): Recent Activity displays the exact value
returned by the API, without time-zone conversion.** UTC-to-local conversion
was removed:

- `api/profile.py`: `_as_utc` deleted; summary and recent-achievement dates remain naive as returned by RetroAchievements.
- `widgets/activity_entry_card.py`: `_format_timestamp` replaces `_format_local`, without `astimezone()`.
- `core/activity_feed.py`: subtract `_SORT_EPOCH` instead of using `datetime.timestamp()`, which interprets naive dates as local time.

Live verification: `API raw = 2026-08-06 18:41:51` →
`card shows = 2026-08-06 18:41`.

**Accepted consequence:** the display is one hour behind the UTC+1 wall
clock; a user seen a minute ago can appear to have been seen an hour ago.
The chosen criterion was matching the website. Do not reintroduce
`astimezone()` here.

##### Investigation leading to this decision

Three rounds reported the app as one hour ahead of the website. The
technical diagnosis remains valid and explains the code comments:

- **The website displays absolute UTC, matching the raw API value**,
  confirmed by the user's Following-page screenshot. Local conversion
  made both displays individually correct in different time zones; the
  final decision chose the website's time zone.
- **The API returns UTC regardless of account Locale.** Changing that
  preference to Lisbon did not change the output.

##### Proving the time zone without circular reasoning

The initial argument, that a value close to `utc now` must be UTC, assumed
the person was currently playing. That assumption itself relied on the
UTC interpretation. A person last online an hour earlier could fit either
reading. Independent evidence was required:

**1. The field advances in real time.** Repeated `RichPresenceMsgDate` reads:

| Measurement (UTC) | Returned value | Difference |
|---|---|---|
| 17:54:00 | 17:53:51 | 9 s |
| 18:07:42 | 18:05:51 | 1m51s |
| 18:11:40 | 18:09:51 | 1m49s |

The field advanced 4m00s while 3m58s elapsed. A fixed last-seen event an hour
in the past would not advance this way.

**2. Cross-check an unlock with an established time zone.** Between the first
and second measurements, achievement `264251` appeared at `17:58:29`. Its
`Date` field had already been proven UTC using an award with explicit
`+00:00`. `LastPlayed` for the same game, 3065, was `18:09:51`. If that were
Lisbon local time, it would mean `17:09:51` UTC: **49 minutes before an
unlock in that same game**, which is inconsistent.

Practical rule: establish time zones using a proven event or repeated
measurements, not an app-versus-website difference. If activity looks stale
again, inspect `RECENT_ACHIEVEMENTS_WINDOW_MINUTES` (seven days) and
`FOLLOWED_USERS_LIMIT = 30` in `activity_feed_service.py`.

### 2.3 Median-time synchronization — external limit

**This was not delivered at the requested speed.** These approaches were tested live:

| Strategy | Measured result |
|---|---|
| Sequential, 0.30 s | About 3.3 games/s, stable |
| Sequential, 0.25 s | HTTP 429 for 8 of 60 games |
| Sequential, 0.10 s | HTTP 429 after about 9 calls |
| Four parallel threads, 0.30 s each | HTTP 429 for 26 of 40 games |

RetroAchievements limits the **aggregate rate**, not each connection.
Parallelism makes this worse. The effective ceiling is about three requests
per second, so roughly 11,800 games require about an hour. Going faster
risks an account block.

**Mitigation:** `GameRepository.list_ids_missing_median_time()` prioritizes
(1) installed games, (2) games on consoles with local ROMs, and (3) the rest.
The six installed games finish in about two seconds, making the filter
useful for the actual library before the full backfill finishes. HTTP 429
responses receive exponential backoff (1 s, 2 s, 4 s), rather than aborting
the entire run.

**Alternative awaiting the user's decision:** backfill only consoles with
local ROMs, reducing about 11,800 games to a few hundred. This was proposed
but had not received an answer.

---

## 3. Files touched by the latest fixes

**Statistics (§2.1):**

- `src/retrocheevos/api/profile.py`: pagination and `COMPLETION_PROGRESS_PAGE_SIZE`.
- `src/retrocheevos/core/profile_stats.py`: `BEATEN_AWARD_KINDS`, weighted completion at that stage.
- `src/retrocheevos/database/schema.py`: `ALTER_TABLES_V14`.
- `src/retrocheevos/database/migrations.py`: register v14.
- `src/retrocheevos/models/profile.py`: `stats_revision`.
- `src/retrocheevos/database/repositories/profile_repository.py`: persist/read the column.
- `src/retrocheevos/services/sync_service.py`: `PROFILE_STATS_REVISION` and invalidation.

**Recent Activity (§2.2):**

- `src/retrocheevos/gui/pages/home_page.py`: interval, `showEvent`, reentrancy guard.
- `src/retrocheevos/api/profile.py`: `get_user_summary`, `RawUserSummary`, naive dates.
- `src/retrocheevos/services/activity_feed_service.py`: `_latest_unlock`, summary-based reads.
- `src/retrocheevos/models/activity_feed.py`: `last_seen_at`.
- `src/retrocheevos/core/activity_feed.py`: sort by `last_seen_at`, `_SORT_EPOCH`.
- `src/retrocheevos/widgets/activity_entry_card.py`: `_format_timestamp`, Last seen / Last unlock.

**Median times (§2.3):**

- `src/retrocheevos/database/repositories/game_repository.py`: priority ordering.
- `src/retrocheevos/services/sync_service.py`: `_fetch_median_time_with_retry`, backoff.

**Block 11 (§5):**

- `src/retrocheevos/gui/pages/rom_location_page.py`: new, replaces `library_page.py`.
- `src/retrocheevos/services/library_service.py`: `scan_rom_folder`, `_hash_in_place`.
- `src/retrocheevos/models/library.py`: `RomFolderScanResult` replaces `WatchFolder*`.
- `src/retrocheevos/gui/pages/settings_page.py`: two sections removed.
- `src/retrocheevos/gui/main_window.py` and `gui/pages/home_page.py`: `rom_location` key.
- `src/retrocheevos/library/console_detection.py`, `gui/dialogs/match_rom_dialog.py`: docstrings.

**Other Block 10 fixes:**

- `src/retrocheevos/gui/main_window.py`: `NAV_ITEMS = ["Home"]`.
- `src/retrocheevos/gui/pages/leaderboards_page.py`: deleted.
- `src/retrocheevos/gui/pages/explorer_page.py`: Download removed, bar always visible.
- `src/retrocheevos/gui/delegates/explorer_delegates.py`: no `download_requested`.
- `src/retrocheevos/gui/models/explorer_table_model.py`: 1h 30m formatting.
- `src/retrocheevos/widgets/continue_playing_game_row.py`: `QProgressBar` restored.
- `src/retrocheevos/core/dashboard.py`: no longer excludes games at 100%.
- `src/retrocheevos/main.py`: multi-resolution icon.

---

## 4. Important decisions and findings

- **API pagination:** `API_GetUserCompletionProgress.php` caps results at 100
  and reports `Total`. Check `Count` / `Total` before treating a seemingly
  truncated endpoint as incorrect data.
- **`API_GetUserSummary.php` is the rich endpoint.** A single call provides
  `UserPic`, `RichPresenceMsg`, `RichPresenceMsgDate` (last seen), `LastGame`
  (title/console/icon), `Awarded` (last-game earned/total), and
  `RecentAchievements`. It covers the feed except playtime, which still
  needs `API_GetGameInfoAndUserProgress.php`. At this historical point,
  reducing three calls per user to two remained an optimization opportunity.
- **Naive RetroAchievements timestamps are UTC**, proven by comparing the
  same event in `API_GetUserAwards.php` (explicit `+00:00`) and
  `API_GetUserRecentAchievements.php` (naive). Treat new offset-free date
  fields as UTC; any conversion belongs only in presentation, subject to
  the raw-UTC display decision in §2.2.
- **Rate limit:** roughly three requests per second.
  `CATALOG_SYNC_CALL_DELAY_SECONDS = 0.3` is near the usable minimum. Do not parallelize.
- **New API calls must use `_with_rate_limit_retry`.** Spacing reduces but
  does not eliminate HTTP 429. Previously only median-time synchronization
  had backoff; `sync_consoles`, `sync_games_for_console`, `sync_profile`
  (three unpaced calls), and event progress could abort Sync Everything on
  a single 429. A new account makes the largest initial run, about
  84 + 3 + 237 requests, making it particularly vulnerable. Exhausted
  retries intentionally have different policies: `_with_rate_limit_retry`
  **raises**, because a missing console creates a persistent catalog gap;
  `_fetch_median_time_with_retry` returns `None`, leaving a cell for the next run.
- **`API_GetGameProgression.php` exists** and returns
  `MedianTimeToBeatHardcore` (live example: Diablo → 326 seconds). One request per game.
- **At this point, `achievements` / `user_achievements` were always empty.**
  `sync_game_details` and `sync_account_progress` had no callers.
  `AchievementRepository.get_mastered_game_ids()` therefore returned
  `set()`, as documented in the method. Mastery filters needed
  `GameCompletionRepository.get_finished_game_ids()`, reading `highest_award_kind`.
- **Catalog counts:** 12,041 synced versus 11,307 on the website. The
  difference included 237 Events (console 101), 13 Standalone entries (102),
  and 498 subsets (`[Subset - …]`); excluding them gave 11,304. The shared
  `_BROWSABLE_GAME_CLAUSES` in `game_repository.py` governs both `search()`
  and `count_all()` so those counts remain consistent.
- **Events are games** on console 101, already carrying the correct
  `retroachievements_url`; the Events section needed no new API.
- **Taskbar icon (item 5):** no regression was reproduced. `main.py` matched
  the commit, the 889×889 `icon.png` loaded with `QIcon.isNull() == False`,
  and `AppUserModelID` was set. A multi-resolution icon was a plausible
  improvement, not a confirmed fix. If it persisted, the suggested next
  investigation was the Windows icon cache outside the code.
- **Continue Playing and Library coexist by design.** Continue Playing is
  the quick Home shortcut with small, recent-game cards; Library (Block 13)
  is the full view with larger frames.

---

## 5. Remaining blocks

### Block 11 — ROM Location — complete (2026-08-06)

Library became **ROM Location** and stopped organizing files. It points to
folders already organized by the user and detects their contents.

**Renamed:** `library_page.py` → `rom_location_page.py`, `LibraryPage` →
`RomLocationPage`, and the `library` key → `rom_location` in
`main_window.py::_menu_pages` and `home_page.py::USER_MENU_DESTINATIONS`.
The latter constant is in `home_page.py`, not `main_window.py` as the plan claimed.

**Deleted:** `gui/dialogs/watch_folder_scan_dialog.py`, `library/organizer.py`,
`models/rom_destination.py`, `database/repositories/rom_destination_repository.py`,
`library/quick_link_suggestions.py`, `models/quick_link.py`,
`database/repositories/quick_link_repository.py`, and `tests/library/test_organizer.py`.

> **Deliberate deviation:** `tests/library/test_zip_extraction.py` was kept.
> Although the plan called for deleting it, `zip_extraction` still serves
> `console_detection` through `find_single_rom_member` and the new
> `_hash_in_place` through `extract_member`. Removing it would remove coverage of live code.

**Cleanup:** `library_service.py` lost `preview_watch_folder_scan`,
`apply_watch_folder_scan`, `ALREADY_EXTRACTED_DIRNAME`,
`RomDestinationNotConfiguredError`, and seven destination/quick-link
functions. `RomFolderNotFoundError` stayed because the new scan uses it.
`models/library.py` lost three `WatchFolder*` dataclasses; Settings lost
ROM Destinations and Quick Links.

**Added:** `library_service.scan_rom_folder(rom_folder_id, progress_callback)`
and `models/library.py::RomFolderScanResult`. It traversed with `rglob`,
skipped registered files, detected the console, hashed, and registered
**without moving, renaming, or deleting files**. Only confident detections
were registered. Ambiguous and unknown files were returned for display,
rather than guessed.

- **ZIPs:** `_hash_in_place` extracts the single member into a temporary
  directory, hashes that member as RetroAchievements does, then discards
  the copy. The registered `file_path` remains the ZIP on disk, which is
  also the path passed to the emulator.
- **No review dialog:** the old dialog requested approval because the next
  step moved files. The new scan does not move anything and runs directly.

**Unchanged:** `rom_destinations` and `console_quick_links` remained in
`schema.py`, orphaned but inert. Dropping them would require a destructive
migration outside this block.

**Verification:** a temporary database and real files, never the user's
`database/retrocheevos.db`: three ROMs registered from five files; ambiguous
`.iso` and unknown `.txt` reported without guessing; subfolders traversed;
ZIP hash matched its member and differed from the ZIP itself; **all five
files remained intact**; the second pass registered zero and skipped three.
All 24 existing tests passed with
`PYTHONPATH=src python -m unittest discover -s tests -t .`; omitting the path
configuration prevented package discovery.

### Blocks 12 + 13 — Lists — complete (2026-08-06)

Implemented together at the user's request before deeper Block 11 testing.

**Migration v15** (`CREATE_TABLES_V15`):
`user_list_definitions(id, account_id, name, slug, is_predefined, created_at)`
with unique `(account_id, name)`, `user_lists.list_id`, and conversion of
existing rows. Each populated `list_type` became a definition and existing
memberships referenced it. **No data was lost.** The v2 unique index on
`(account_id, game_id, list_type)` initially remained; the new partial index
was `(account_id, game_id, list_id) WHERE list_id IS NOT NULL`.

> **Partial indexes require the predicate in `ON CONFLICT`.** Runtime tests
> caught `ON CONFLICT(account_id, game_id, list_id) DO NOTHING` failing with
> `ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint`.
> The correct form is `ON CONFLICT(...) WHERE list_id IS NOT NULL DO NOTHING`.

**`slug` distinguishes predefined and user-created lists.** Predefined
slugs use `ListType` because code reasons about their behavior (Explorer
hides blocked entries; Library derives from ROMs). User lists have
`slug = NULL`, with no name-based branching. `ListType` gained `LIBRARY`.

**The old handoff's enum trap was fixed:** `get_list_types_for_game` called
`ListType(row['list_type'])` and failed for arbitrary user list names. It
was replaced by `get_list_ids_for_game`. `_row_to_definition` also tolerates
unknown slugs instead of raising.

**Library** (Block 13) is calculated from ROMs currently installed, not
stored in membership rows. Storing memberships would require every scan
to maintain them. `add_to_list` rejects Library with an explanatory
`ValueError`. New `widgets/installed_game_frame.py` provides a large cover
whose entire image launches the game through `mousePressEvent`, without a
button underneath; right-click remains available for a future menu.

**Blocked** is a regular list with a minus button on
`GameCard(show_remove=True)`. Its duplicate Settings management was removed.
Explorer resolves Block **by slug** through `block_requested`, so renaming
Blocked does not break blocking.

**Existing storage reused:** the requested per-console folder path already
existed in `rom_folders.console_id`; only its UI was missing. The section
below Library writes to that table, making folders immediately scannable
through ROM Location. `rom_destinations` was not revived.

**Four duplicate `LIST_ACTION_LABELS` maps reduced:** `game_card.py` and
`explorer_delegates.py` receive `list_options` / `set_list_options`; the map
in `lists_page.py` was removed. The remaining `explorer_filter_bar.py` map
filtered by slug and served a different purpose.

**Validation errors are raised outside `get_connection`.** Inside that
context, ordinary refusals such as duplicate names were logged as database
rollback failures with tracebacks, obscuring actual failures.

**Verification:** a temporary v14 database with legacy data migrated
successfully: no missing `list_id`; blocked games hidden from other lists
and restored after unblocking; Library changed from empty to `['Delta']`
after inserting a ROM; manual Library insertion refused; empty and
case-insensitively duplicate names refused; predefined-list deletion
refused; a user list named blocked list did not merge with Blocked. All
24 existing tests passed.

#### UI adjustments after Library and Blocked worked (2026-08-06)

1. **Library grid increased from three to eight columns**, with
   `InstalledGameFrame.COVER_SIZE` reduced from 180 to 104. These values
   were coupled; changing only one caused horizontal scrolling.
2. **Only Library and Blocked were special entries at the top.** Rename
   disabled for both; Delete restricted to user lists. The UI no longer
   offered actions the service always rejected.
3. **Blocked and custom lists use new `widgets/list_entry_row.py`:** cover,
   title, console, and minus; no Play or overflow menu. The remaining
   predefined Want to Play, Playing, Completed, and Abandoned lists still
   used `GameCard` at this stage.
4. **ROM Folders removed from Settings**, now per-console below Library's grid.
5. **ROM Location page and menu entry removed.** Library absorbed both the
   installed-game grid and folder management, scanning, and Match to Game.

> **Match to Game and unmatched ROMs had to move together.** Otherwise a
> ROM with an unmatched hash would be invisible: it is absent from the
> matched-game grid, leaving no way to identify it. This is why Library has
> an Unmatched ROMs section below the grid.

6. **Primary navigation list removed.** It contained only Home after other
   destinations were absorbed, consuming 160 px to navigate to the current
   page. The main layout became vertical: history bar above pages. Removing
   the list also removed its `currentRowChanged` / `itemClicked` path,
   previously implicated in destroying a live `QThread` during startup.

Headless verification (`QT_QPA_PLATFORM=offscreen`), with seven selector modes:

```text
Blocked      widgets={ListEntryRow}       rename=False delete=False
Library      widgets={InstalledGameFrame} rename=False delete=False folders_shown=True
Playing      widgets={GameCard}           rename=True  delete=False
My Backlog   widgets={ListEntryRow}       rename=True  delete=True
user menu: [('lists', 'Lists'), ('settings', 'Settings')]
```

> **Verification lesson:** importing a module does not run widget
> constructors. An invalid `ImageLoader(self)` call reached the user and
> prevented startup because that constructor accepts no parent. At minimum,
> GUI checks must construct `MainWindow` and every page offscreen and call
> `refresh()`. The historical session used `scratchpad/verify_ui.py`; recreate
> it if useful. Explicitly tear down widgets before process exit, or Qt can
> abort during shutdown and mask the outcome with a misleading exit code.

### Visual overhaul — RetroAchievements theme (2026-08-07)

**Color sources:** the website's Cloudflare protection returned HTTP 403 for
non-browser requests, including `requests` and WebFetch. Browser tools also
crashed the Claude app on this machine (as noted in §4). The alternative was
the open-source `RetroAchievements/RAWeb` repository:
`resources/css/theme.css` defines the palette with CSS custom properties.
No colors were inferred from screenshots.

Useful upstream files through `raw.githubusercontent.com`, without
Cloudflare: `resources/css/theme.css`, `typography.css`, `button.css`,
`table.css`, and `progress.css`.

**`gui/styles.py`** grew from a scrollbar stylesheet into a theme module.
Constants mirror upstream CSS variable names so the mapping stays
verifiable. It uses the default unconfigured-account **dark/gold** palette:

```text
--bg-color              #1a1a1a      --link-color (gold)   #cc9900
--box-bg-color          #232323      --link-hover-color    #eeeeee
--embed-color           #161616      --text-color          #c8c8c8
--embed-highlight-color #2a2a2a      --heading-color       #d2d2d2
--divider-color         #5a5a5a      --text-color-muted    #4b4b4b
```

Typography: Verdana/Arial, CSS `small`. Buttons: 4 px radius, embed
background, accent text, embed-highlight border; hover uses embed-highlight
and link-hover. Tables: odd rows `rgba(50,50,50,.3)`, hover
`rgba(128,128,128,.2)`, 4/8 px cell padding. Progress: 6 px, hardcore gold
`#cc9900`, softcore blue `#0b71c1`.

**Two deliberate Qt adaptations:** muted `#4b4b4b` was nearly invisible on
flat Qt panels, so `TEXT_DIM` handles secondary text and muted is reserved
for disabled content. `FONT_SIZE_PT` replaces browser-root-relative `small`.

Invented widget colors were removed: Recent Activity purple `#8a63d2`,
Home/event blues `#4a90e2`, and grays such as `#b0b0b0`. At this stage a
hex-literal search outside `styles.py` returned no matches.

> **`QLabel` inherits `QFrame`.** A generic panel-border rule applied to
> every label, surrounding text with empty rectangles. A `QLabel { border:
> none }` rule alone was insufficient: equal-specificity QSS rules are
> resolved by file order, so it had to appear **after** the `QFrame` block.
> Both errors became visible only in a rendered image. `QLineEdit`,
> `QListWidget`, and `QScrollArea` also inherit `QFrame`.

> **Verify visual work by rendering and inspecting it.** Compilation or
> headless construction cannot validate a stylesheet because QSS can fail
> silently. The effective method was `page.grab().save(...)` followed by
> viewing the PNG. On the Windows setup used here, the offscreen plugin
> produced missing-glyph boxes, misleadingly suggesting a font problem.
> The normal Windows plugin could grab a widget that had never been shown.

Image inspection also exposed the cover grid being squeezed into one and a
half rows: both folder-section `QListWidget`s requested their entire
`sizeHint`. They received `setMaximumHeight` limits.

#### Navigation arrows removed (2026-08-07, twelfth round)

The `‹ ›` buttons and all supporting code were removed: `_history`,
`_history_index`, `_on_back`, `_on_forward`, `_update_history_buttons`, the
`record_history` argument to `_show_page`, and `HISTORY_BUTTON_*` constants.
With four destinations available from the avatar menu, now including Home,
browser history added unnecessary interface overhead. `_show_page` returned
to simply switching pages.

The top layout also shrank: `WINDOW_MARGIN = 0`, central `setSpacing(0)`,
and `HEADER_GAP = 4` before the page. Header and pages already own their
side margins. Measurements: zero arrow buttons; header at `y=0`, height
99 px; page beginning at `y=103`.

#### Global QSS overrode every `setFont()` (2026-08-07, eleventh round)

Measuring why TrophyTracker would not grow revealed that stylesheet
`font-size` overrides `setFont()`. Since `gui/styles.py` set it on `QWidget`,
programmatic sizing throughout the app was silently discarded:
`APP_NAME_FONT_DELTA`, `POINTS_FONT_SIZE`, and `TRUE_POINTS_FONT_SIZE`.
The app name rendered at 15 px instead of about 33 px; points stayed at body
size despite `POINTS_FONT_SIZE = 32`.

Sizes were moved into those labels' `setStyleSheet` declarations. For the
points' `setFixedHeight(metrics.ascent())`, `ensurePolished()` must run
before `QFontMetrics`; otherwise measurements use the previous font and
clip digit tops, the same trap as card captions.

Measured at window width 1200 px with account statistics:

```text
logo(RC)      101x64  x=11   bottom=71
TrophyTracker 267x42  x=112  bottom=71   <- same baseline as logo
12,132        169x43  x=930
24,325         82x24  x=1017 bottom=71
header height = 87px (unchanged)
```

#### Uniform card sizes (2026-08-07, tenth round)

Caption height used `lineSpacing() * len(lines)`, depending on each title.
One-line titles produced shorter cards than two-line titles and an uneven
grid. All cards now reserve the worst case:
`CAPTION_LINES = MAX_TITLE_LINES + 1`. Short titles leave a blank final line;
top alignment keeps titles anchored while console text moves lower for
long titles.

> The verification previously checked only clipping and missed uneven
> sizes. It now compares `sizeHint()` across titles at the same cover size,
> for three Library sizes and three Continue Playing sizes.

#### Wrap before eliding (2026-08-07, ninth round)

`widgets/text_layout.py::wrap_lines` wraps on words up to the maximum line
count and elides only if the title still does not fit. Eliding immediately
had discarded words that would fit on a second line.

At this stage caption height came from the produced lines,
`lineSpacing() * len(lines)`, rather than a predetermined value; the later
uniform-card adjustment above reserved the worst case instead.

```text
 94px  Shadow of the Colossus  -> ['Shadow of the', 'Colossus']
154px  Castlevania: Symphony…  -> ['Castlevania: Symphony', 'of the Night']
 94px  Supercalifragilistic…   -> ['Supercalifrag…']   (single word: elide)
```

Titles use up to two lines, console names their own line. The 24-size sweep
reported zero clipping.

#### The actual text-clipping fix (2026-08-07, eighth round)

> **The earlier no-clipping test checked nothing.**
> `scratchpad/verify_noclip.py` skipped labels when
> `label.pixmap() is not None`. PySide6 returns an empty `QPixmap`, not
> `None`, so the whole sweep skipped every label and reported zero clipping
> while 31 labels clipped. The correct check is
> `not label.pixmap().isNull()`.
>
> **Actual cause:** elision used `QFontMetrics(label.font())` before widget
> polishing. Before `ensurePolished()`, `font()` reflects the default font,
> not the stylesheet's font. Text was measured small and drawn larger.
> Correct order: polish → measure → elide → size. Height now uses
> `lineSpacing()` instead of `height()`, and elision allows `edge - 6px`
> because QLabel rounds layout dimensions. The real sweep covered 13
> Library sizes and 11 Continue Playing sizes with a long title: zero clipping.

**Console abbreviations:** `library/console_names.py` maps PlayStation
Portable → PSP, Game Boy Advance → GBA, and SNES/Super Famicom → SNES, only
in captions. Tooltips retain full names. Unknown consoles pass through
unchanged, producing at most a longer caption.

**Header:** avatar increased from 54 to 64 px; `header_widget` received
11 px side margins so the logo aligns vertically with search and the avatar
has edge clearance. The header is in `MainWindow`, outside the page layout,
so it did not inherit page margins.

#### Elided captions and compact header (2026-08-07, seventh round)

> Earlier caption attempts used a cover-height ratio (0.36), then three
> font-derived lines, but still clipped at some sizes. Required line count
> depends on both title and width; choosing height alone cannot solve all
> combinations. The temporary solution replaced wrapping with
> `QFontMetrics.elidedText`: one elided line fits the width, so two lines
> fit two line heights. A deliberately long title was swept through all
> 13 Library sizes and 11 Continue Playing sizes and reported zero clipping;
> the eighth-round notes above explain the subsequent correction to that test.

**Slider minima:** Continue Playing 75 px, Library 100 px; the former
module-wide minimum became an instance parameter.

**Header:** points 26→32, true points 17→18, while the band became shorter.
Avatar 72→54 px with frame 12→8; logo 52→42; `header_layout.setSpacing(0)`
removed excess spacing. `AlignBottom` aligned logo, name, points, and avatar
across every page because `MainWindow` owns the shared header.

#### Cards scale with the slider; larger header (2026-08-07, sixth round)

> **The card must shrink with its image.** Even after deriving columns from
> available width, fixed caption heights (Library 54 px, Continue Playing
> 42 px) and constant margins left a 40 px cover inside a card sized for
> 150 px artwork. Caption size, margins, and spacing were changed to cover
> ratios. Below 90 px, the caption is hidden and the tooltip supplies its
> name: readable two-line text does not fit thumbnail width.
>
> Measured card scaling:
>
> ```text
> cover   Library        Continue Playing
>   40    46x46  1.15x     46x62  1.55x
>  160   174x238 1.49x    174x258 1.61x
> ```
>
> A second cause of the same symptom was `ContinuePlayingGameRow` using
> horizontal `Preferred`: a single card absorbed a full grid column around
> a tiny image. Both axes became `Fixed`, matching `InstalledGameFrame`.

**Larger header:** logo 32→52, avatar 48→72, points 13→20, true points
11→14, app name +8, statistics +2. The avatar already dictated band height,
so enlarging the other elements did not displace content.

#### Slider and Recent Activity fixes (2026-08-07, fifth round)

> **Column count ignored available width.** Continue Playing used
> `6 * COVER_SIZE_BASELINE // cover_size`, a fixed-baseline ratio returning
> exactly six columns at 40 px. `QGridLayout` stretched them into six mostly
> empty boxes. `_continue_playing_columns()` now measures the viewport.
>
> ```text
> Continue Playing (viewport 920)     Library (viewport 1360)
>   40px -> 13 columns                  40px -> 20 columns
>  125px ->  5                         160px ->  7
> ```

**Half-width Library:** `_grid_columns` already measured the viewport, but
`MainWindow._show_page` called `refresh()` before layout, when the viewport
reported a placeholder size. Without a later resize, that narrow count
persisted. `showEvent` now recalculates on actual display, and `refresh()`
updates `_last_grid_columns`.

> **Slow return to Home:** `refresh()` cleared Recent Activity and forced
> `show_loading=True` on every visit, discarding correct entries and waiting
> about six seconds for identical replacements. `_activity_cache` now keeps
> the last complete feed, paints it immediately on return, and refreshes
> quietly. Loading appears only on a cold start. Clear the cache without an
> active account, or the next account briefly sees the previous feed.

#### Visual adjustments (2026-08-07, fourth round)

> **Recent Activity flicker came from silent refresh.**
> `_refresh_activity_feed(show_loading=False)` retained old cards, but the
> first new streamed entry cleared them and showed one card, then added the
> others one at a time. Every 30 seconds the content appeared to disappear
> and return. Streaming now applies only to the initial load through
> `_stream_activity_entries`; background refresh renders the complete list
> once. `_render_activity_entries` suppresses repaint during teardown/rebuild,
> avoiding a one-frame flash.

- **Slider:** moved to `valueChanged` for live resizing. `STEP = 10` limits
  a complete drag to about a dozen rebuilds rather than hundreds. Width is
  fixed at 160 px with `addStretch` afterward; a full-width slider looked
  like the section's main control. Maximum cover sizes: Home 125 px,
  Library 160 px.
- **Vertical Continue Playing cards:** cover, title, then progress bar,
  like Library. The old horizontal strip no longer suited a resizable,
  clickable cover.
- **No fixed Library grid cap:** columns use actual viewport width rather
  than `GRID_TARGET_WIDTH = 980`, which limited wide windows to four covers
  and wasted the right side. `resizeEvent` rebuilds only when column count changes.
- **Navigation arrows above the logo**, with `HISTORY_BAR_GAP` and
  `HEADER_GAP`, to distinguish them from page-specific controls.
- **Home first in the avatar menu:** it is the root page, special-cased by
  `_on_menu_navigate`, not duplicated in `_menu_pages`, which would create
  two Home instances and two activity timers. Clicking the avatar goes
  directly Home; hovering opens the menu. Previously both gestures did the same thing.

#### Shared header, cover-size slider, and related work (2026-08-07)

**Header on every page:** `HomePage.header_widget` packages logo, name,
points, statistics, and avatar; `MainWindow` mounts it above
`QStackedWidget`. One instance avoids four profile fetches and signal sets.
`refresh_header()` is separate from `refresh()`, since opening Settings
should not trigger several seconds of Recent Activity API calls.

**Cover-size slider:** `widgets/cover_size_slider.py` serves Library and
Continue Playing. Initially it connected `sliderReleased`, not
`valueChanged`, because rebuilding a large library on every drag pixel
stalled the window; the displayed number still followed dragging. It was
not persisted: introducing a view-preference table and migration for one
readily adjusted slider was deferred until more preferences justified storage.
The later fourth-round notes describe the switch to stepped live updates.

Library columns became derived from cover size instead of a separately
maintained constant, eliminating the mismatch that previously caused
horizontal scrolling.

**Events heading:** a centered QLabel with
`styles.SECTION_HEADER_STYLESHEET`, sharing the gold box styling above it.
A disabled QPushButton would misleadingly look like an unavailable action.

**Taskbar icon:** `MainWindow` set a single-size `QIcon`, later replaced by
`main.py`'s multi-resolution icon. Removing the competing assignment left
one source. `_build_app_icon` now logs path, dimensions, and AUMID because
the previous two reports were not reproducible. Windows caches taskbar
icons by AUMID. The historical note recorded an AUMID change as
`TrophyTracker.App` → `TrophyTracker.App`; those identical recorded values
cannot establish an actual identifier change.

> **Explorer button spacing required layout changes.** Buttons were laid
> out left-to-right from a margin, leaving any width beyond `sizeHint()`
> unused at the right while Play and + remained adjacent. `_button_rects`
> now distributes buttons across the cell, using `_BUTTON_SPACING` as a
> minimum. Two constant-only adjustments had failed.

#### Post-theme visual adjustments (2026-08-07)

1. **More room for Events:** `SIDEBAR_MIN_WIDTH` 300→400, maximum 380→480,
   `EVENTS_MIN_HEIGHT` 260→320. Minimum width matters because a `stretch=0`
   sidebar does not request extra space beyond its contents.
2. **Blue points restored:** `styles.POINTS_BLUE = #4a90e2`. Gold remains
   reserved for interactive buttons and links; gold read-only values made
   the whole page look interactive.
3. **Visible app name changed to TrophyTracker:** window title, header,
   `APP_USER_MODEL_ID`, and logs. Only visible strings should change;
   the lowercase Python package remains `retrocheevos`, and broad replacement
   can break imports. The original recorded replacement pair repeated the
   same display name and should not be treated as an executable instruction.
4. **Continue Playing and Recent Activity expand vertically:** removed
   `_center_column_filler` with `stretch=1`, giving each group `stretch=1`.
   `_expand_explorer` still works because hidden widgets contribute no stretch.
5. **Continue button removed:** the cover launches the game through
   `mousePressEvent`, as in Library. The progress bar remains.
6. **Explorer spacing:** `_BUTTON_SPACING` 4→14 and `_BUTTON_MARGIN` 4→8,
   visually separating Play and +.

> **Two layout traps visible only in rendered output:** giving a group
> `stretch=1` also stretched a lone Continue Playing card around a 40 px
> cover. `setAlignment(AlignTop)` alone was insufficient; the card also
> needed a vertical `QSizePolicy.Policy.Fixed` to refuse extra height.

### Library/Lists restructuring (2026-08-06, second adjustment round)

**Library became its own page**, `gui/pages/library_page.py`, in the avatar
menu alongside Lists and Settings. It never behaved like a regular list:
no stored memberships or manual additions, and a unique grid renderer.
`ListType.LIBRARY` stopped acting as a list. The blocked-game exclusion
lives in `core/lists.py::get_installed_games` beside other list rules,
avoiding duplicate logic.

**Only Blocked remains predefined.** `PREDEFINED_LISTS` was reduced to one
entry. The user confirmed Want to Play, Playing, Completed, and Abandoned
were empty and preferred creating personal lists; those four were deleted.

**Migration v16** deletes those definitions and memberships.
**Migration v17** drops the v2 `(account_id, game_id, list_type)` index.

> **The v2 index was not redundant; retaining it in v15 was a mistake.**
> All user lists store `CUSTOM_LIST_TYPE_MARKER` in `list_type`, so the
> index effectively restricted each game to one user-created list forever.
> Adding the same game to a second list raised `UNIQUE constraint failed`.
> Tests caught it. The correction is migration 17, not an amendment to 16,
> because databases already at 16 would never see an edited migration.

**Explorer consequence:** the Lists pill previously offered Want to Play /
Playing filters and Completed / Abandoned toggles. It now derives choices
from the account's actual lists with `ExplorerFilterBar.set_list_options`.
`ExplorerFilters.list_types_any_of` became `list_ids_any_of`. Completed /
Abandoned toggles were removed without losing finished-game exclusions:
`game_completion`, the RetroAchievements record rather than a manual list,
still excludes finished games unconditionally. This also removed the last
of four duplicate `LIST_ACTION_LABELS` maps.

**Visual adjustments:**

- `InstalledGameFrame`: cover 104→150 px, grid eight→six columns; those
  values remained coupled. An unconstrained text label overlapped the
  image; fixed size and top alignment now reserve `TEXT_HEIGHT` below it.
- `ListEntryRow`: three iterations progressed from huge vertical panels,
  through a sparse 32 px cover in a 40 px row, to a **64 px cover in a
  76 px row**. Console text moved from a separate right-aligned label into
  parentheses after the title, such as `Beta (Game Boy Advance)`. The title
  takes the stretch, keeping the minus button at the right without a large
  gap before a separate console label.

Headless verification:

```text
predefined lists shipped: ['Blocked']
user menu: [('library','Library'), ('lists','Lists'), ('settings','Settings')]
Lists dropdown: ['Blocked', 'My Backlog']        <- no Library
Blocked      widgets={ListEntryRow}  rename=False delete=False
My Backlog   widgets={ListEntryRow}  rename=True  delete=True
LibraryPage grid: ['InstalledGameFrame']  cover=(150,150) frame=(164,222)
Explorer Lists pill: ['My Backlog']
```

Data checks migrated a legacy v14 database through v17: only Blocked and
its memberships survived, blocked games were hidden from both a user list
and Library, and the same game could belong to two user lists.

### Block 12 (original plan, now historical) — User-created lists (high risk)

- **Migration v15** (v14 was already used):
  `user_list_definitions(id, account_id, name, is_predefined, created_at)`,
  unique `(account_id, name)`; `user_lists.list_id INTEGER`; new unique
  `(account_id, game_id, list_id)` index.
- **Why a new table:** putting names in `list_type` would merge a user list
  named blocked with the predefined one and leave nowhere for metadata.
  The original plan said not to touch the existing v2 index; the later v17
  correction above supersedes that instruction.
- **Migrate existing data in the same version:** convert Want to Play,
  Playing, Completed, Abandoned, and Blocked into definitions and populate
  `list_id`. The user explicitly required no data loss.
- **Trap:** `ListRepository.get_list_types_for_game` converted values through
  `ListType(row['list_type'])`, failing on names outside the enum.
- **`ListType` becomes a predefined marker**, `BLOCKED` and later `LIBRARY`.
  `core/explorer.py` and `core/dashboard.py` filters use `list_id`.
- **UI:** create/rename/delete in `lists_page.py`; + menus in
  `explorer_delegates.py` and `GameCard` derive from definitions. At this
  point four duplicate `LIST_ACTION_LABELS` maps existed in game_card,
  explorer_delegates, lists_page, and explorer_filter_bar.
  `list_action_requested = Signal(int, object)` already accepted an ID as
  its second argument without changing its signature.
- **Blocked leaves Settings:** three isolated widget blocks and two methods.

### Block 13 — Library playlist (low risk, depends on Block 12)

The original plan called for a second predefined, automatic list, resolved
from `library_repository.get_installed_game_ids()` without `user_lists` rows.

- New `widgets/installed_game_frame.py`: large cover frame, title below,
  the entire image clickable through `mousePressEvent` → `play_requested`.
  Existing widgets used explicit buttons. Reuse `ImageLoader` with a
  `game_id` filter as in `ContinuePlayingGameRow`.
- Add an `ImageLoader` and Library-specific `refresh()` branch to
  `lists_page.py`; `_clear_grid()` remains type-independent.
- The name Library becomes available after Block 11 renames the old page.

---

## 5b. Update checks (notification only)

`version.py::APP_VERSION` is the only version source; other code should not
hardcode it. At startup, `services/update_service.py` checks GitHub's
`releases/latest` in a `ServiceWorker`, never on the UI thread. A newer
version displays `widgets/update_banner.py` above the header.

Rules to preserve:

- **Never authenticate this request.** The endpoint is public; the stored
  RetroAchievements key must not be sent to GitHub. A test rejects an
  `Authorization` header or `params`.
- **Every negative result, including offline operation, returns `None`.**
  Startup should not show an error because Wi-Fi is disconnected. Log the reason.
- **Compare versions numerically.** Lexically, `1.10.0 < 1.9.0`, which would
  silently stop update notifications at the tenth release. Covered by tests.
- **Unparseable release tags mean no update.** Otherwise the banner could
  remain even after an update because the version cannot be understood.
- **Dismissal stores a version**, not a boolean, in
  `preferences_service.KEY_DISMISSED_UPDATE_VERSION`. Later releases then
  notify automatically. `update_service.should_notify` intentionally makes
  the opposite parsing choice from `is_newer`: an unreadable dismissal
  means show the banner, so corrupt stored data cannot silently suppress
  every future update.
- **Known limitation:** `set_str` does nothing without an active account,
  so a dismissal before login lasts only that session. Preferences are
  account-scoped; adding separate anonymous storage for this one value was
  considered disproportionate. Persistence works after login.

Historical release procedure: increment `APP_VERSION`, create
`v<APP_VERSION>`, and publish a release against it. The checker reads
releases, not tags, so a tag can exist while a build is still being prepared.

## 5c. Security and final cleanup

**API keys leaked into plaintext logs.** `client.py` used
`logger.exception` for `requests.RequestException`; urllib3's traceback
included a URL such as `/API/X.php?z=user&y=<key>`. Offline operation, slow
DNS, or a timeout could expose it in `logs/retrocheevos.log`, the file users
share for troubleshooting. The class promise that credentials were never
logged was therefore false.

Both routes were closed:

1. Direct logging now uses `logger.warning` and
   `redact_credentials(str(error), key)`.
2. `raise ... from error` preserved the original in `__cause__`;
   `main.py::_log_uncaught_exception` logs `exc_info`, including that cause
   and its URL. Changed to `from None`, preserving useful redacted
   diagnostics in the new exception's message.

**Rule:** sanitize anything derived from a request error with
`redact_credentials` before writing it. Covered by `tests/api/`.

**Four image caches wrote inside the bundle:** `game_images`, `user_pics`,
`local_covers`, and `activity_icons` derived paths from `__file__` without
handling `sys.frozen`, unlike `connection.py`. Invisible from source, this
caused writes beside the executable, silently failing in Program Files;
one-file extraction discarded caches on each launch; and caches belonged
to the installation instead of the user, potentially sharing profile
photos between Windows users. `local_covers` was especially serious because
manually selected covers cannot be downloaded again. All paths now go
through the single decision point in `retrocheevos/paths.py`.

**Orphan cleanup:** three passes converged as removing one dead layer
exposed another. Deleted `core/cache_policy.py`,
`database/repositories/leaderboard_repository.py`, `models/leaderboard.py`,
18 functions/classes, and eight imports. Remaining apparently uncalled
`rowCount` / `headerData` methods are Qt overrides invoked by the framework.

**Migration v22 drops orphan tables:** `notification_settings` and
`leaderboard_cache`. The name is not `leaderboards`; confirm actual schema
names before writing DROP statements. Both tables were verified empty in
two databases. Migration 21→22 preserved counts for notifications,
accounts, games (12,042), and user_lists, with successful `integrity_check`
and clean `foreign_key_check`.

Historical CREATE statements remain intentionally, as in v20: a fresh
database creates those tables and v22 immediately drops them. Editing old
migrations would desynchronize databases that already applied them; briefly
creating an unused table is the smaller cost.

**Explorer Play/+ spacing regressed twice and now has a test.** The cause
was row-dependent `ActionsDelegate.sizeHint`, not `_BUTTON_SPACING`.
Installed rows display Play and +; other rows only +. Column width is shared
by every row, but `ResizeToContents` samples only a limited number
(`resizeContentsPrecision`, default 1000) out of about 12,000. If none of
the sampled rows are installed, the column fits one button and installed
rows below paint + outside it.

Before: column 51 px, `sizeHint` 69 px, 9 px overflow. After: column 70 px,
15 px button gap, no overflow. Small catalogs or different sorting can hide
the bug. `tests/gui/test_actions_delegate_width.py` enforces the actual
invariant: `sizeHint` must not depend on the row.

**Hash-based ROM matching was structurally impossible.** The only writer
of `game_hashes`, `sync_game_details`, had no callers. An empty table meant
`find_game_id_by_hash` always failed and ROMs lacked `game_id`. This
explained two installed games in Explorer (manually matched) versus 74 in
Library: both counting rules were correct; matching was missing.

`sync_all_game_hashes`, exposed by Explorer's Sync ROM Hashes, addresses this:

- **Resumable** through `list_ids_missing_hashes`, essential for an hour-long
  run. At this historical point, a genuinely hashless game was requested
  again each time because fetched-empty and never-fetched were
  indistinguishable. Repeating that request was chosen over a new marker
  column; later work may supersede this tradeoff.
- **`replace_hashes`, not `add_hash`:** no unique `(game_id, hash)` constraint
  existed, so rerunning would duplicate rows.
- **Finish with `library_service.rematch_unmatched_roms()`.** Matching
  otherwise happened only during scanning, and rescans intentionally skip
  registered files. No API calls are needed because `installed_roms.hash`
  already stores the hash.

**Cost:** `sync_game_details` makes three requests per game (extended
metadata, median time, hashes): about 36,000 requests and three hours. Only
the hash call supports ROM matching. Default `full_details=False` therefore
makes one request per game, about 12,000 and one hour. The dialog allows choosing.

**API keys moved from SQLite to the OS vault.**
`services/credential_store.py` uses Windows Credential Manager
(`WinVaultKeyring`), encrypted under the OS account. `accounts.api_key`
remains a deliberate fallback, not dead code:

- **Graceful degradation:** keyring resolves its backend at runtime, and a
  backend may be unavailable. Without a vault, the key remains in SQLite
  with a log warning; the storage improvement must not prevent startup.
- **Clear the column only after confirmed vault storage.** A key stored
  nowhere would permanently break account authentication.
- **`migrate_plaintext_keys()` runs at startup, not as a schema migration.**
  Vault availability varies by OS and machine; `PRAGMA user_version` cannot
  represent it. A database migrated on a machine without a vault must retry later.
- **Run `VACUUM` afterward.** UPDATE removes a logical value but SQLite can
  retain its bytes in freed pages, readable with a hex editor; without
  compaction the storage change would be cosmetic.
- **`packaging/TrophyTracker.spec` needs hidden imports** for
  `keyring.backends.Windows` and `win32ctypes.core`. Entry-point resolution
  is invisible to PyInstaller's static analysis; without them the frozen
  app silently falls back to database storage.

**Deferred questions recorded at this point:** the original note contained
an incomplete item about operation without OS-vault integration; it did
not identify further action. Fourteen Python files had UTF-8 BOMs: Python
imports them, but analysis tools may need `utf-8-sig`, as the dead-code
scanner did.

## 5d. ROM hashing: RAHasher and the licensing decision

`library/hashing.py` originally computed whole-file MD5 without
RetroAchievements' console-specific rules (NES/N64 headers, disc tracks,
PlayStation executable hashing). Reimplementing formats was abandoned
partway: `library/ciso.py` for `.cso` was written; CHD and RVZ were not.

**Decision:** invoke the official `RAHasher.exe` through
`library/rahasher.py` as a subprocess. It uses the same `rcheevos/src/rhash`
sources as RetroAchievements, avoiding divergence from a separate implementation.

**Historical licensing decision:** RAHasher is built from RALibretro,
GPL-3.0, although underlying rcheevos is MIT. The recorded design treats a
separate subprocess as aggregation rather than linking and does not change
TrophyTracker's license. Redistributing the binary still requires license
text and corresponding source or a written offer. The bundled notices are
`RAHasher-COPYING.txt` and `RAHasher-SOURCE.txt` under `tools/`.
`packaging/TrophyTracker.spec` refuses to bundle the helper without both.
When replacing it, update the version and SHA-256 in `RAHasher-SOURCE.txt`.

**Formats verified with real ROMs and RAHasher 1.8.3 x64:** PS1/PS2 `.chd`,
`.cue`, PS2 `.iso`, and Dreamcast `.gdi`, all previously failing. The
Windows project defines `HAVE_CHD` in `src/RAHasher.vcxproj`; Linux CI uses
`HAVE_CHD=1`. Without this flag the helper prints CHD not supported and
returns 0; verify it before substituting a custom build.

**Fallbacks remain necessary:**

- `.cso`: RAHasher reports Could not open track. `library/ciso.py` returns
  the correct hash, matching the equivalent ISO in the catalog; it is not redundant.
- `.rvz`: RAHasher reports Not a Gamecube disc. At this historical point it
  was deliberately excluded from `console_catalog`; otherwise whole-file
  MD5 fallback would record an unusable hash. Revisit that behavior when
  adding the extension. Later roadmap work supersedes the old RVZ support state.

**Missing helper is supported.** The app falls back to built-in hashing.
`rahasher.find_executable` intentionally does not cache discovery: placing
an executable in `tools/` or beside the app is detected without restarting.

## 6. Suggested checks when resuming this historical work

1. Confirm Home statistics **98 / 56 / 56.75%**. Revision 2 forces a first-run
   resync even when a revision-1 cache entry is recent.
2. Treat Recent Activity time zones as closed (§2.2): **raw UTC**, matching
   the website and one hour behind the local clock used in this session.
   Read that decision before reopening the investigation.
3. Check six Continue Playing columns and the wider sidebar.
4. Open Lists → Library, add a real per-console folder, and run Scan Folder.
   This covers the remaining real-ROM validation from Block 11, previously
   tested with synthetic files, and the new folder section.
5. Check eight covers per row, cover-click launching, minus buttons in
   Blocked and a custom list, and create/rename/delete actions.
6. Decide whether median-time backfill should cover only consoles with ROMs (§2.3).
7. The numbered blocks ended here; subsequent work is new.
