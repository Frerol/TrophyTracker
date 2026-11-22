# TrophyTracker — UI specification

## Status and references

This document separates the current desktop behavior from the proposed visual
revamp. The [roadmap](../planning/DevelopmentRoadmap.md) owns task status.
The [reviewed UI proposal](ui-proposal-reviewed.html) and
[product fit review](ProposalReview.md) define the revised design direction.
The [supplied HTML](ui-proposal.html) remains an original visual reference;
its controls are not evidence of implemented features.

## Current desktop navigation

`gui/main_window.py` provides Home, Library, Lists and Settings through a
220 px sidebar (`gui/sidebar.py`): brand, the four destinations (Ctrl+1–4),
the displayed account with its menu, and the version. Explorer is embedded in
Home behind catalog search and filters. There is no separate Profile,
Dashboard, Achievements or Systems page. Home shows the points/stats summary.

Each destination keeps its view state while the user is elsewhere: Home's
catalog search, filters and results, and the scroll position of Library and
Lists. Selecting the current destination again returns it to its root view
(Home collapses the catalog results). Detail screens (R21) open on top of the
current destination, which stays selected; Back (Alt+Left) returns to it
unchanged. Choosing a destination in the sidebar or changing the displayed
account closes open details. The window's minimum size is 1024×720; rows of
filter chips and sync buttons wrap instead of being clipped.

Saved credentials and displayed identity are separate. Saving another account
in Settings does not switch the interface. The user explicitly selects the
displayed account in Settings or the sidebar account menu, which opens on
click. One account is active at a
time; restart restores that choice. Sign out preserves saved data. Delayed
results from a previous selection must never update the new account's screen.

## Current screens and actions

### Home

- Header with "Last synced …" freshness and Sync now (forced profile sync;
  disabled with the running job's name while another job holds the slot).
- Catalog search with "Explore catalog" and "Your lists" shortcuts; the
  embedded Explorer, its filters and catalog sync buttons appear only while
  the catalog is open.
- Metric cards: points, true points, beaten games (with a leaderboard link)
  and mastered games (average completion in its tooltip). Missing data shows
  "—" and "Not synced yet".
- Continue Playing list beside Recent Activity (about 2:1; stacked below
  ~1100 px window width). Rows show cover, console, "X/Y achievements"
  (RetroAchievements' combined count), "NN% complete" or "Progress
  unavailable", and a Play button that is disabled with a reason when no
  emulator is configured. Unmatched ROMs say so and keep cover/removal
  actions in a "⋯" menu.
- Followed-user Recent Activity, with cached results and partial-failure feedback.
- Now Playing, distinct from an achievement-unlock event stream.
- A badges and event awards summary leading to the Awards view; no
  standalone profile page.

### Awards (detail screen from Home)

- Badges and Event awards tabs with the account's synced awards; images
  load only for visible items. Empty: "Sync profile to load awards."
- Events tab: event games with progress and the new-events notice, which
  marks the events as read. Back (or Alt+Left) returns to Home unchanged.

Profile synchronization is opportunistic when stale and participates in the
same job coordination as manual synchronization. Activity refresh keeps its
existing backoff; no fixed five-minute profile polling is introduced.

### Explorer

A sortable model/view table over the cached achievement-enabled catalog.
Search input is debounced; snapshot reads run in a worker. Core owns console,
list, installed, game-type and median-time filters. Blocked, beaten and mastered
games are excluded from suggestions; completed/abandoned list rules retain
their existing toggles. Numeric sorting and return-state preservation matter.
Actions include Play where available, list/block operations and external RA
links. No recommendation engine, genre filter or full leaderboard UI is implied.

### Library

Account-scoped installed ROMs and configured folders, independent of Explorer's
catalog exclusions. Local games can be unmatched or lack an achievement set.
Scanning indexes existing files without moving, renaming or downloading them.
Selected/all-folder scans expose progress and cancellation; forced verification
rehashes existing files. Manual matches and user-selected covers are preserved
according to the explicit matching policy.

Keep manual matching, cover customization, emulator configuration, missing-file
feedback and Play accessible. No automatic Watch Folder organizer exists.

Since R22 the page is a model/view cover grid (about 200 px minimum card
width: 4 columns at 1240 px, 3 at 1024 px) with the indexed-ROM count, a
Folders… dialog (the shared ROM folder editor, which R24 also puts in
Settings) and a Scan menu (all folders, verify hashes, single file) with
progress, Cancel and Details… for skipped paths. Search covers titles and
file names; filters are All, In progress, Mastered, Unmatched and System.
Cards show "X/Y achievements" (combined count), "NN% complete", "Progress
unavailable" or "No catalog match", and a Play button drawn disabled with
"No emulator" when the console has none. Play checks that a file still exists
(offering removal) and offers "Configure emulator", which opens Settings on
that console. The context menu adds Match to game… and Choose cover… (unmatched
ROMs), Change match… (matched games, to correct a wrong automatic match;
asks which file when there are several), Use automatic match (undoes a
manual choice: hashes the file again in the background, then goes back to
that hash's match or to Unmatched) and Remove from
Library. Matching is automatic by hash at scan time, after Sync ROM Hashes
and on Verify hashes; manual choices are never overwritten by those passes.
After a scan or re-hash, consoles whose unmatched ROMs have no catalog hashes
yet get them fetched automatically (one request per console, once per console
per session, under the job slot with progress and Cancel), then matching runs
again. The Unmatched filter says when hashes are missing (with Fetch catalog
hashes) or, once they exist, that the file is probably a hack or other dump;
files without any hash say their format cannot be read (GameCube and Wii
RVZ/WIA/GCZ are hashed through Dolphin's dolphin-tool when installed, by
converting only the start of the disc). There is no cover size slider.

### Lists

Account-scoped definitions and memberships support custom collections. Blocked
is the special collection used by Explorer exclusions. Do not impose a fixed
set of list names. Distinguish rename, remove membership and delete list;
neither membership removal nor list deletion deletes a ROM file.

### Settings and dialogs

Saved accounts and explicit display selection, removal confirmation, masked API
keys, emulator configuration and profile sync. Emulator setup supports offline
console selection, executable discovery, launch arguments, libretro cores and
supported Flatpak discovery. Preserve update-banner and window preferences.
ROM Destinations and Quick Links were removed; do not restore their dialogs.

## Proposed visual revamp — not implemented

- Dark purple surfaces, gold achievement/progress accents and turquoise
  secondary highlights; Inter text and Space Grotesk headings/branding.
- The same four main destinations, with compact account-aware navigation.
- Home cards sourced from existing points, true points, beaten and mastered
  fields; Continue Playing, social activity, Now Playing and awards remain.
- A virtualized Library cover grid with local search, progress filters and
  explicit Play/configuration actions.
- Explorer retains its efficient table and separate catalog search semantics.
- Contextual game and achievement detail screens are planned. Achievement
  counts/unlock state need an account/mode-aware service, on-demand refresh and
  cache wiring before controls are enabled. Missing data must remain unknown.
- No initial rarity sorting, release year, comments publishing/replies,
  translation, instant unlock detection or new automatic polling preferences.
  Community discussions are opened externally on RetroAchievements.
- Settings follows the reviewed account/sync/folder/emulator layout. Folder
  management entry points share the same editor rather than independent state.
- Lists has a reference board and remains directly reachable.
- Brand A/C comparisons remain pending; no new icon is selected by this document.

The HTML's synthetic values, sample emulator choices and paths are never
runtime defaults. Its colored cover blocks are placeholders for real cached
artwork and deliberate fallback states. Font licenses and offline packaging
must be validated before runtime assets change.

## Interaction and quality requirements

Common Play/list/RA actions should be reachable without unnecessary detail-page
navigation. Long I/O runs off the GUI thread with visible, non-blocking progress.
Shared API pacing is cancellable; sync jobs are mutually coordinated. Closing
requests cancellation and keeps the event loop alive until workers and image
signals have drained, bounded by the shutdown timeout, instead of destroying
running Qt objects; work that outlives the budget stays referenced.

Preserve bounded image caching, debounced search, cancellation and partial
progress. Cached content remains useful after refresh failures. Show no-account,
loading, empty, offline, partial-success and retryable-error states. Distinguish
unknown data, zero progress, locked achievements and no achievement set.

Validate keyboard focus/order, accessible names, labels beyond color, text
contrast and 100/125/150/200% scaling. Production layouts must adapt from
1024×720 through 1920×1080; the 1240×780 HTML is only a reference canvas.
Optional motion must be short/disableable and must not trigger network work.

Fullscreen, resize, active-worker close, account switching, data recovery and
packaged startup remain release checks. Native Windows validation is pending;
Linux and offscreen checks do not replace it.
