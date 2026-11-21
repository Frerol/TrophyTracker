# UI proposal — product fit review

Reviewed on 2026-11-20 against the current desktop code, the project goal and
the user's requirement for one explicitly selected displayed account.

## Decision

Keep the dark purple surfaces, gold progress/achievement accents, turquoise
secondary highlights and compact native-desktop direction. Revise the flows
and data promises before implementing the visual redesign.

The [reviewed proposal](ui-proposal-reviewed.html) is the implementation planning
reference. The user's [six-board source](ui-proposal.html) is preserved unchanged
by this review. Its generated controls and sample values do not define product
requirements. The reviewed artifact has eight static boards: the six supplied
subjects plus Explorer and Lists, which are existing product flows.

This review does not implement the new runtime interface or complete R16–R27.
The account selection, worker coordination and ROM recovery fixes are separate
runtime changes, documented in the [completion audit](../validation/RoadmapCompletionAudit.md).

## Product boundary

TrophyTracker is a desktop companion for RetroAchievements: browse an
achievement-enabled catalog, organize existing local ROMs and account-specific
lists, inspect cached progress, and launch configured emulators. Progress is
obtained from RetroAchievements; the app does not award achievements or detect
unlocks by reading emulator memory. Scanning indexes existing files; it does not
move, rename, delete or download ROMs.

Linux is the current public release target. Windows builds and checks exist,
but native Windows validation is still pending. Android is a separate planned
achievement-tracking companion, without ROM management or emulator launching.

## Changes to the supplied reference

| Reference element | Reviewed decision | Reason / implementation source |
| --- | --- | --- |
| Home, Library, Achievements, Systems, Settings sidebar | Home, Library, Lists, Settings; catalog search enters Explorer from Home | Matches `gui/main_window.py`; restores the existing Lists flow. Achievements are reached from game detail; emulator/system configuration belongs in Settings. No empty destinations. |
| Unnamed implicit signed-in account | Explicit displayed account in the sidebar/header and Settings | Multiple credentials may be saved, but saving another account must not select it. Account data, worker results and caches remain isolated. |
| Ranking, global achievement denominator, near-mastery and system totals | Points, true points, beaten games and mastered games | These fields exist in `models/profile.py` and `ProfileRepository`. The other metrics have undefined data contracts or denominators. |
| Unlock/mastery event feed | Existing followed-user Recent Activity, with cached/partial states | `activity_feed_service.py` supplies activity/presence, not the drawn event stream. Do not relabel it as an unlock event. |
| Missing Now Playing and badges | Keep both visible in Home's hierarchy | Existing `now_playing_panel.py`, badges and event awards remain reachable. |
| Library cover grid | Keep as a proposed presentation of local installed-ROM records | `library_service.py` is the source. Mastered/no-set games are distinct from unmatched ROMs and unknown progress. |
| Library search | Search local games only | It must not replace Home/Explorer's catalog search. |
| Missing Explorer reference | Add a sortable catalog table reference | Preserve existing filters, median time, actions and suggestion exclusions in `core/explorer.py` and `explorer_table_model.py`. |
| Missing Lists reference | Add account-scoped collections and explicit membership actions | `lists_page.py`, `core/lists.py` and `user_list_definitions` support custom lists; only Blocked has special behavior. |
| Game release year and rarity sorting | Remove year/rarity from the initial UI; sort by supported fields such as points | `models/game.py` and `models/achievement.py` do not store those fields. Any later addition needs its own data contract. |
| Achievement RetroPoints, author/dates, global recent unlocks | Remove unsupported fields; show points, account/mode state, unlock date when known and sync freshness | The existing achievement DTO stores ID, game, title, description, points and badge; the unlock DTO stores account, hardcore and timestamp. |
| Comments, publishing, replies and translation | Open the achievement/community page externally | The current API adapter has no comment read/write/translation integration. The companion should not promise an unimplemented social platform. |
| Reindex on startup and fixed five-minute sync | Manual scan/sync controls, existing conservative refresh behavior | No new permanent polling, startup scan or watch-folder workflow is authorized by a visual checkbox. |
| Instant unlock notification preference | Remove | TrophyTracker does not monitor gameplay for achievement unlocks; API updates can lag. Notifications need separate event sourcing and product scope. |
| Test connection button | Save credentials and separately select the displayed account | The current account setup saves credentials; an API-validation UI would require its own implementation. Profile sync already reports authentication failures. |
| Add system | Configure emulator for a known console | The existing console selector works offline. This action does not invent consoles or change file-format support. |
| Folder scan ages and system/file counts | Avoid unsupported timestamps and use clearly illustrative folder state | `RomFolder` has no last-scan timestamp. Do not invent freshness from unrelated metadata. |
| A/C brand preference | Keep both concepts pending a real size/platform comparison | No final icon was selected. Artwork remains a separate R17 decision. |

## Screen and data mapping

| Reviewed board | Existing behavior reused | Work still required for the revamp |
| --- | --- | --- |
| Home | Profile stats, Continue Playing, account-specific header, followed activity, Now Playing, badges/events, embedded Explorer | New layout/components; loading, offline and partial-feed variants; retain account guards and request pacing. |
| Library | Account-scoped ROMs/folders, scans, forced hash verification, manual matching, local cover selection, emulator launching | Virtualized cover grid and local search/filter presentation; show no-set, unmatched and missing-emulator states distinctly. |
| Game detail | Game/achievement repositories, completion data, guarded Play/list/open-on-RA actions | New destination, account/mode-aware detail service, on-demand achievement/unlock fetch and cache integration. Existing storage alone is not a complete screen. |
| Achievement detail | Achievement fields and user unlock records | New destination and refresh path; explicit hardcore/softcore rules; return to the originating game/view. External community link only. |
| Settings | Saved accounts, account selection/removal, profile sync, offline console/emulator configuration and updates | Restyle controls and unify folder-management entry points with Library. Preserve the full emulator dialog (path, arguments, core, discovery/Flatpak) and account-removal confirmation. |
| Explorer | Cached catalog table, filters, background snapshot reads, debounce, numeric sorting, Play/list/block/RA actions | Restyle without replacing model/view with one widget per game; retain state and selection when returning from detail. |
| Lists | Definitions, memberships, Blocked special handling, rename/delete/remove actions | Restyle and integrate detail entry. Predefined names in examples must not become mandatory collections. |
| Brand | Existing runtime artwork and proposed A/B/C treatments | Component tokens, font packaging/licenses, icon-size comparisons and a final brand decision. |

Achievement totals must be scoped to the selected game/account and mode.
Do not add hardcore and softcore counts together. Missing data is unknown,
not zero or proof that a game has no achievements. A local playable ROM may
lack an RA association or supported achievement set and must remain in Library.
Explorer is a suggestion catalog with its existing unconditional exclusions;
those exclusions must not hide mastered/no-set local games from Library.

Play is offered only when a local file and an appropriate configured emulator
are available. Otherwise show an actionable configuration/matching state.
Launching does not guarantee achievement support for every emulator; the
emulator and ROM must be compatible with RetroAchievements where applicable.

## Navigation and retained actions

Home exposes catalog search; Library exposes local search; Lists remains a
primary destination. Game and achievement details are contextual destinations,
not new empty top-level sections. Back restores the original view's search,
filters, selection and scroll. Settings and the account area expose selection,
sign out and saved-account management. A restart restores the previously
explicit selection; signing out preserves saved account data.

Folder configuration may be opened from Library and Settings, but both entry
points must share one editor and data model. Scan all, selected-folder scan,
forced hash verification, manual matching, local cover customization, missing-
file feedback and emulator configuration remain available. Removing a folder
or list must not imply deleting ROM files. Removing an account requires a
clear explanation of the local data that will be removed.

## Validation and remaining design work

The reviewed HTML is self-contained and static, with bundled licensed Latin
font subsets (with their SIL Open Font License notices) and no external scripts,
API requests or form submission.
Reference navigation links jump between boards; application controls illustrate
intended behavior. The source-language reference and proper names are preserved
in the original file; the reviewed copy uses English.

Eight boards were rendered locally at a 1240×780 canvas using software Qt
WebEngine; text/layout were inspected, including the additional Explorer/Lists
flows. This is not runtime GUI validation or an accessibility certification.

R16 still needs a complete dialog/action inventory, small-window variants and
an explicit service contract for detail data. R17/R25/R26 must validate focus,
keyboard operation, contrast, scaling, unknown/offline/partial/error states and
all component states in the real Qt interface. The fixed-width reference is
not a responsive production layout.
