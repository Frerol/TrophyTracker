# TrophyTracker — Android Roadmap

Status: planned. No Android application or APK has been implemented yet.

## Product goal

Build a mobile companion for following RetroAchievements progress. Users
should be able to see their profile, recent games, achievement unlocks and
game completion from their phone, including previously cached information
when offline.

Progress comes from the RetroAchievements API. The Android app will not
detect achievements itself or read emulator memory. Refreshes show data
already published by RetroAchievements; updates are not guaranteed to be
instantaneous.

## Scope of the first release

- One saved RetroAchievements account, using its username and API key.
- Home with account points, recent games and recent unlocks, as available
  through the API.
- Played games with search and completion filters.
- Game details with artwork, achievement descriptions, points and separate
  hardcore/softcore progress where available.
- Filters for locked and unlocked achievements.
- Local favorites and a backlog list.
- Manual refresh, bounded refresh on opening the app and visible last-sync
  timestamps.
- Offline access to previously synchronized records and cached images.
- Settings for credentials, cache and local data removal.

Excluded: ROM scanning, ROM hashes, emulator discovery or launching,
downloads of games, gameplay monitoring, desktop/mobile list synchronization,
continuous background polling and notifications while the app is closed.
Local lists belong to this installation; they are not automatically synced
to RetroAchievements or the desktop application.

## Technical direction to validate

Start with a small Python/PySide6 Android packaging experiment to measure
how much of the existing application can be reused. Evaluate Qt Quick/QML
for the touch interface rather than carrying desktop widget layouts over.
This is a proposed direction, not a completed compatibility assessment.

Keep API access and business rules outside the UI. Audit `api/`, `models/`,
`core/`, `database/` and the relevant `services/` for reuse; do not assume
every service is independent of desktop behavior. Adapt data paths,
credential storage, application lifecycle and network workers behind
platform interfaces. Keep the desktop application working throughout.

The Android installation has its own database and cache. Reuse schema and
repository code only where it helps; avoid depending on desktop folders,
ROM records or a complete catalog download to display an account's progress.
Never embed the private Codeberg repository's credentials in the APK.

## Phase 0 — Feasibility and stack decision

Tasks:

- Inventory the imports and dependencies needed for profile/game progress.
- Build and install a minimal APK on a real Android phone.
- Validate Python/PySide6 packaging and a touch-oriented screen.
- Make one account/profile request without exposing credentials in logs.
- Demonstrate app-private SQLite storage and an Android-appropriate secure
  credential-storage adapter; do not assume desktop `keyring` works.
- Record APK size, startup behavior, supported Android versions/ABIs and
  build requirements.
- If packaging or essential dependencies are impractical, compare a native
  Kotlin/Compose frontend with the Python approach before implementing the
  remaining screens. A native rewrite would need a new estimate.

Exit criterion: a reproducible APK build, a successful profile query on a
real phone and a written stack decision backed by the experiment.

## Phase 1 — Mobile foundation

Tasks:

- Add the Android entry point and platform adapters without changing the
  desktop entry point.
- Implement navigation: Home, Games, Lists and Settings, with game details
  opened from the relevant list.
- Add account setup, credential validation and logout/local-data controls.
- Configure app-private database, migrations and bounded image caching.
- Run network requests away from the UI thread; handle cancellation and
  activity recreation without starting duplicate sync jobs.
- Define loading, empty, offline and error states.

Exit criterion: account setup persists across restarts; navigation remains
responsive; credentials are excluded from logs and insecure fallbacks.

## Phase 2 — Achievement tracking

Tasks:

- Implement Home, played-game list and game/achievement details.
- Fetch account-level data first and load achievement details on demand.
- Reuse the current API rate-limiting/error-handling logic after auditing it
  for the mobile lifecycle.
- Support manual refresh and conservative refresh when resuming the app.
- Distinguish hardcore and softcore results without double-counting.
- Show cached results while refreshing, with clear synchronization status.

Exit criterion: profile totals and a sample of game unlocks agree with the
corresponding API results; failures preserve the last successful data;
repeated taps do not create duplicate network work.

## Phase 3 — Lists and offline use

Tasks:

- Add local favorites/backlog and search/filter controls.
- Keep list changes and cached account progress across restarts.
- Make previously loaded screens usable in airplane mode.
- Bound cache growth and provide cache clearing without deleting lists or
  credentials. Explain separately what full local-data removal deletes.
- Handle expired credentials, interrupted requests and API throttling with
  actionable messages and bounded retries.

Exit criterion: cached games and achievements open offline; uncached data
is clearly identified; local lists survive cache clearing and app restarts.

## Phase 4 — Device testing and private beta

Tasks:

- Check small screens, font scaling, touch targets, contrast, system Back
  behavior and portrait/rotation behavior.
- Test app backgrounding, process termination, network changes and low
  storage on real devices, plus the declared minimum Android version.
- Add focused tests for reused progress rules, cache/account isolation and
  credential redaction. Run the desktop regression suite after shared-code
  changes.
- Set application ID, icon, version and release build configuration.
- Produce a signed APK and document installation and in-place upgrades.
- Keep signing secrets outside Git and back up the signing key securely.
- Distribute through the private repository and collect beta feedback.

Exit criterion: a signed APK installs and upgrades without losing local
data, core flows pass on the device matrix and no known issue prevents
account setup, progress viewing or offline viewing.

## Milestones and planning estimate

These are provisional effort ranges for one experienced developer working
primarily on this project. They include implementation and focused checks,
but exclude store review and extended beta feedback. AI assistance does not
remove the need for real-device validation.

| Phase | Deliverable | Initial effort range |
| --- | --- | --- |
| 0 | Installable proof of concept and stack decision | 3–5 working days |
| 1 | Mobile foundation and account setup | 4–6 working days |
| 2 | Profile, games and achievement tracking | 7–10 working days |
| 3 | Local lists and offline experience | 4–6 working days |
| 4 | Device validation and signed private beta | 5–8 working days |

Total: roughly 23–35 working days, or 5–7 full-time weeks before an extended
beta period. Re-estimate after Phase 0; packaging problems, a stack change
or limited Android experience can extend this substantially.

The desktop version is currently 0.1.0. Choose Android's first release
version at release preparation; this roadmap does not tag or publish a
mobile release.

## Later candidates

Only after the first release is stable: multiple saved accounts, public
profile browsing, achievement comparison, widgets, optional background
updates/notifications, export/import of local lists and optional
desktop/mobile synchronization. Each requires its own API/platform
feasibility check and scope decision.

## Next action

Implement Phase 0 only: install a minimal APK, query a profile, verify local
storage/credentials and decide the stack before committing to the full UI.
