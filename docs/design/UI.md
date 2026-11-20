# TrophyTracker — UI specification

## Status and references

This document separates the current desktop behavior from the proposed visual
revamp. The [roadmap](../planning/DevelopmentRoadmap.md) owns task status.
The [reviewed UI proposal](ui-proposal-reviewed.html) and
[product fit review](ProposalReview.md) define the revised design direction.
The [supplied HTML](ui-proposal.html) remains an original visual reference;
its controls are not evidence of implemented features.

## Current desktop navigation

`gui/main_window.py` provides Home, Library, Lists and Settings. Explorer is
embedded in Home behind catalog search and filters. There is no separate
Profile, Dashboard, Achievements or Systems page. The shared header shows the
displayed account, points/stats and account menu across destinations.

Saved credentials and displayed identity are separate. Saving another account
in Settings does not switch the interface. The user explicitly selects the
displayed account in Settings or the avatar menu. One account is active at a
time; restart restores that choice. Sign out preserves saved data. Delayed
results from a previous selection must never update the new account's screen.

## Current screens and actions

### Home

- Continue Playing and guarded Play actions for local games.
- Points, true points, beaten/mastered/completion statistics.
- Badges and event awards; no standalone profile page.
- Followed-user Recent Activity, with cached results and partial-failure feedback.
- Now Playing, distinct from an achievement-unlock event stream.
- Always-visible catalog search and embedded Explorer.

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
signals have drained, instead of destroying running Qt objects.

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
