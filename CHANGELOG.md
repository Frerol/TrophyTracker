## 0.1.0 — TrophyTracker

- Rename the application, build outputs and documentation to TrophyTracker.
- Preserve existing data and credential identifiers for compatibility.
- Disable automatic update checks against the original project's releases.

## 1.1.1 — 2026-11-20

- Reject stale account-bound Home worker results across account switches/logout.
- Add cooperative cancellation and orderly shutdown across sync/scan/activity/image workers.
- Add application-wide job coordination and shared API pacing with Retry-After handling.
- Detect changed ROMs at previously scanned paths via size+mtime fingerprint; rehash and preserve manual matches.

## 1.1.0 — 2026-11-19

- Add Linux AppImage packaging.
- Allow offline console selection and editing saved emulator settings.
- Add cancellable discovery of native executables, AppImages and installed Flatpaks.
- Save Flatpak application IDs and installations, and launch them through Flatpak.
- Keep console dropdowns bounded and scrollable.
- Detect Wii/GameCube RVZ and WIA ROMs, including Wii folder scans before catalog matching.
- Load ROM thumbnails by platform/name from Libretro, local images and GameTDB disc covers, with caching and manual overrides.
- Add live Home achievement tracking with current-game detection, unlock highlights and periodic refresh.
- Fix shared-path ownership and account changes during ROM scans.
- Fix ZIP rehashing, Linux path comparisons, pending API key updates and quoted emulator arguments.
