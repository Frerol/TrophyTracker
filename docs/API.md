# TrophyTracker — API

## 1. Source of Truth

- All game/achievement/profile data comes from the **RetroAchievements
  API** — never HowLongToBeat, never third-party scrapers.
- BeautifulSoup/scraping is allowed **only if absolutely necessary** (i.e.
  no API endpoint covers the need) — this should be the exception, not the
  rule.

## 2. Authentication

- Authentication happens through the RetroAchievements API using the
  user's **API Key** + **Username**, configured in Settings.
- The app supports **multiple accounts**; switching accounts re-scopes all
  API calls and cached/user-specific data (lists, notifications, profile
  stats) to the active account.

## 3. What Gets Fetched

- **Games**: metadata, console, image, game type (Retail/Homebrew/Hack/
  Demo/Prototype), whether it has achievements.
- **Median Time to Beat (Hardcore)**: from RetroAchievements
  (`API_GetGameProgression.php`, field `MedianTimeToBeatHardcore`),
  hardcore-only. This is a **median**, not an average — RA's own field name
  says so, and the app must never call it "Average" in code, DB columns, or
  UI text. Also fetch the sample size behind it
  (`TimesUsedInHardcoreBeatMedian`) and the direct game URL
  (e.g. `https://retroachievements.org/game/4909`).
- **Achievements**: per game, plus per-account unlock state
  (hardcore/softcore).
- **ROM hashes**: RetroAchievements-supported hashes per game, used for
  local ROM matching — never assume compatibility without a hash match.
- **Profile stats**: points, hardcore points, completion percentage, games
  beaten, games mastered.
- **Badges & Event Awards**: owned/missing, current progress.
- **Leaderboards**: friends, daily/weekly/all-time, plus a derived "Games
  Beaten" leaderboard (not a native RA leaderboard).

## 4. Request Policy

- API requests happen **only when needed**: cache miss or explicit user
  refresh/sync — never to satisfy a UI read like search or filtering.
- No request should ever originate from the GUI layer directly — always via
  `Services` → `Core` → `api/` (see `Architecture.md`).
- Long-running or bulk sync operations run in the background and must never
  block the UI thread (see `CodingStandards.md`).

## 5. Caching Relationship

- Every API response that populates the database follows the cache tables
  and invalidation rules defined in `Database.md` §6–7.
- The API layer itself does not decide *when* to refresh — that's a
  Core/Services decision based on staleness rules.

## 6. Out of Scope (for now)

- Downloading ROMs directly from RetroAchievements or any source is a
  **future** feature (`DevelopmentRoadmap.md`, v1.2) and only "if legally
  possible."
