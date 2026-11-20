## Unreleased

- Queue a Home activity refresh for the new account when the previous account's request is still finishing, without duplicating fetches for the same account.
- Make shared API pacing cancellable and release its lock while waiting, so rate-limit penalties no longer block shutdown.
- Close the window without blocking the GUI while background work drains, bounded by the shutdown timeout.
- Coordinate Home's automatic profile sync with the application-wide job slot.
- Clear obsolete automatic ROM matches when a forced rehash finds no catalog match; manual matches are preserved.
- Require explicit selection of the displayed account; saving an account no longer switches to it.

## 0.1.0 — TrophyTracker

- Add CI for the full offscreen suite on Windows/Linux, packaging smoke builds and a non-blocking dependency-upgrade probe.
- Separate reproducible release constraints, development tools and deliberate upgrade testing into `requirements.txt`, `requirements-dev.txt` and `requirements-upgrade.txt`.
- Add GUI lifecycle regressions with populated Explorer results, repeated fullscreen rendering, navigation and worker lifetime.
- Lock release/build dependencies with SHA-256 hashes and universal platform markers.
- Fix Windows cache publication contention and make existing tests portable across Windows/Linux.
- Prepare the Linux 0.1.0 AppImage and an experimental Windows portable build helper.
- Document test commands, CI jobs and the dependency policy.
- Reconcile the roadmap's current status with the shipped code and label the historical record.
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
