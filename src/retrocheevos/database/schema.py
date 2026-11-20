"""SQLite DDL statements for the TrophyTracker schema (Database.md).

`download_sources` (Database.md 3.3) is out of scope — it's flagged as a
v1.2+ feature in DevelopmentRoadmap.md and not part of the MVP.
"""

CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        api_key TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 0,
        last_synced_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consoles (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        icon_path TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        console_id INTEGER NOT NULL REFERENCES consoles(id),
        image_path TEXT,
        genre TEXT,
        game_type TEXT,
        has_achievements BOOLEAN NOT NULL DEFAULT 0,
        median_time_to_beat_hardcore_seconds INTEGER,
        times_used_in_hardcore_beat_median INTEGER,
        retroachievements_url TEXT,
        last_synced_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_hashes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL REFERENCES games(id),
        hash TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY,
        game_id INTEGER NOT NULL REFERENCES games(id),
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        points INTEGER NOT NULL,
        badge_path TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        achievement_id INTEGER NOT NULL REFERENCES achievements(id),
        unlocked_at DATETIME,
        hardcore BOOLEAN NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rom_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL,
        console_id INTEGER REFERENCES consoles(id),
        watch_enabled BOOLEAN NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS installed_roms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER REFERENCES games(id),
        file_path TEXT NOT NULL,
        hash TEXT NOT NULL,
        console_id INTEGER NOT NULL REFERENCES consoles(id),
        detected_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_lists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        game_id INTEGER NOT NULL REFERENCES games(id),
        list_type TEXT NOT NULL,
        added_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        type TEXT NOT NULL,
        game_id INTEGER REFERENCES games(id),
        message TEXT NOT NULL,
        created_at DATETIME,
        read BOOLEAN NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_settings (
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        type TEXT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT 0,
        PRIMARY KEY (account_id, type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_stats (
        account_id INTEGER PRIMARY KEY REFERENCES accounts(id),
        points INTEGER NOT NULL DEFAULT 0,
        hardcore_points INTEGER NOT NULL DEFAULT 0,
        games_beaten INTEGER NOT NULL DEFAULT 0,
        games_mastered INTEGER NOT NULL DEFAULT 0,
        completion_percentage REAL NOT NULL DEFAULT 0,
        last_synced_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        name TEXT NOT NULL,
        image_path TEXT,
        owned BOOLEAN NOT NULL DEFAULT 0,
        progress REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leaderboard_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        payload_json TEXT NOT NULL,
        last_synced_at DATETIME
    )
    """,
]

# Database.md §8 — indices used heavily by Explorer filters and ROM matching.
CREATE_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_games_console_id ON games(console_id)",
    "CREATE INDEX IF NOT EXISTS idx_games_has_achievements ON games(has_achievements)",
    "CREATE INDEX IF NOT EXISTS idx_games_game_type ON games(game_type)",
    "CREATE INDEX IF NOT EXISTS idx_user_lists_account_list_type ON user_lists(account_id, list_type)",
    "CREATE INDEX IF NOT EXISTS idx_installed_roms_hash ON installed_roms(hash)",
    "CREATE INDEX IF NOT EXISTS idx_game_hashes_hash ON game_hashes(hash)",
]

# Not in the original Database.md schema — added to cache per-account,
# per-game completion percentage (`NumAwarded`/`MaxPossible` from
# `API_GetUserCompletionProgress.php`), powering the Explorer Game Card's
# individual progress bar.
CREATE_TABLES_V3 = [
    """
    CREATE TABLE IF NOT EXISTS game_completion (
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        game_id INTEGER NOT NULL REFERENCES games(id),
        percent_complete REAL NOT NULL,
        last_synced_at DATETIME,
        PRIMARY KEY (account_id, game_id)
    )
    """,
]

# Not in the original Database.md schema — added to power the "Play" button
# (Database.md 3.4): one configured emulator executable per console.
CREATE_TABLES_V4 = [
    """
    CREATE TABLE IF NOT EXISTS emulator_configs (
        console_id INTEGER PRIMARY KEY REFERENCES consoles(id),
        executable_path TEXT NOT NULL,
        arguments_template TEXT
    )
    """,
]

# Not in the original Database.md schema — added to power Watch Folder
# organizing (Architecture.md library/ "console-folder organizer"): one
# user-chosen destination folder per console, distinct from
# `emulator_configs` (that's the emulator executable, this is where ROMs for
# that console should live — different concerns, same one-row-per-console shape).
CREATE_TABLES_V5 = [
    """
    CREATE TABLE IF NOT EXISTS rom_destinations (
        console_id INTEGER PRIMARY KEY REFERENCES consoles(id),
        path TEXT NOT NULL
    )
    """,
]

# Not in the original Database.md schema — one user-chosen reference URL
# per console (e.g. a homebrew catalog or wiki), opened externally via
# QDesktopServices from the Library page. Same one-row-per-console shape as
# `emulator_configs`/`rom_destinations`; the app never fetches or scrapes
# this URL itself, only hands it to the system browser.
CREATE_TABLES_V6 = [
    """
    CREATE TABLE IF NOT EXISTS console_quick_links (
        console_id INTEGER PRIMARY KEY REFERENCES consoles(id),
        url TEXT NOT NULL
    )
    """,
]

# Not in the original Database.md schema — separates community-event badges
# from regular ones on the Profile page's Event Badges tab. Decided once at
# sync time by `core/mapping.py::map_badge`, not recomputed by the GUI.
ALTER_TABLES_V7 = [
    "ALTER TABLE badges ADD COLUMN is_event BOOLEAN NOT NULL DEFAULT 0",
]

# `API_GetUserProfile.php`'s `TotalTruePoints` (RetroRatio-weighted total,
# shown alongside points on RA's own site) and `UserPic` (path fragment for
# the profile photo, `library/user_pics.py`) — both confirmed live.
ALTER_TABLES_V8 = [
    "ALTER TABLE profile_stats ADD COLUMN true_points INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE profile_stats ADD COLUMN user_pic_path TEXT",
]

# Purges games without an achievement set — the app no longer syncs or shows
# these anywhere (`services/sync_service.py`, `database/repositories/
# game_repository.py`), so any such row already sitting in a local DB from
# before that was true is legacy data. Children deleted before the parent
# `games` row; `installed_roms` is unlinked rather than deleted since it
# represents a real, physically-detected ROM file on disk (a future
# rescan/resync simply resolves it to "no matching game" instead of losing
# the detection record).
PURGE_GAMES_WITHOUT_ACHIEVEMENTS_V9 = [
    "DELETE FROM user_lists WHERE game_id IN "
    "(SELECT id FROM games WHERE has_achievements = 0)",
    "DELETE FROM game_completion WHERE game_id IN "
    "(SELECT id FROM games WHERE has_achievements = 0)",
    "UPDATE installed_roms SET game_id = NULL WHERE game_id IN "
    "(SELECT id FROM games WHERE has_achievements = 0)",
    "DELETE FROM games WHERE has_achievements = 0",
]

# The Follow feature (`ListType.FOLLOWING`) was removed — `user_lists` is
# shared, generic infrastructure for every list type (Database.md §4.1), so
# only rows with this specific `list_type` value are cleaned up; the table
# itself stays for Want to Play/Playing/Completed/Abandoned/Blocked.
PURGE_FOLLOWING_LIST_ENTRIES_V10 = [
    "DELETE FROM user_lists WHERE list_type = 'following'",
]

# RA's own per-game award classification (`RawAwardKind` — beaten-hardcore/
# beaten-softcore/completed/mastered), from `API_GetUserCompletionProgress.php`.
# Previously only folded into `profile_stats`' aggregate counts
# (`games_beaten`/`games_mastered`) and discarded per-game — this persists it
# so Explorer can exclude already-beaten games the same way it already
# excludes already-mastered ones (`database/repositories/
# game_completion_repository.py::get_finished_game_ids`).
ALTER_TABLES_V11 = [
    "ALTER TABLE game_completion ADD COLUMN highest_award_kind TEXT",
]

# No "last played" signal existed anywhere before this (confirmed:
# `detected_at` is scan time, `game_completion.last_synced_at` is sync
# freshness, RA's own `LastGameID` field is fetched but unused and only
# covers a single game). Stamped by `services/library_service.py`'s shared
# `_launch_installed_rom` helper on every successful launch — covers matched
# games and unmatched ROMs alike, from every launch entry point in the app.
# Powers Continue Playing's "most recently played first" ordering.
ALTER_TABLES_V12 = [
    "ALTER TABLE installed_roms ADD COLUMN last_played_at DATETIME",
]

# Raw achievement counts alongside the existing percentage. The percentage
# alone can't be shown as "3/12 achievements", which is how the Events
# section on Home reports progress — and events are just games on the Events
# console, so they reuse this table rather than getting one of their own.
# Filled from `API_GetGameInfoAndUserProgress.php` by
# `sync_service.sync_event_progress`; NULL for games only ever seen through
# `API_GetUserCompletionProgress.php`, which reports percentages.
ALTER_TABLES_V13 = [
    "ALTER TABLE game_completion ADD COLUMN achievements_unlocked INTEGER",
    "ALTER TABLE game_completion ADD COLUMN achievements_total INTEGER",
]

# Which version of the stats *formula* produced the cached row.
# `profile_stats` is a cache keyed on freshness (`last_synced_at`), which
# only ever asked "how old is this?" — so when the maths behind
# beaten/mastered/completion changed, every existing row stayed "fresh" and
# kept serving numbers computed the old way, indefinitely. Comparing this
# against `sync_service.PROFILE_STATS_REVISION` lets a formula change
# invalidate the cache the same way an expiry does. Defaults to 0, i.e.
# "pre-versioning", so existing rows re-sync once.
ALTER_TABLES_V14 = [
    "ALTER TABLE profile_stats ADD COLUMN stats_revision INTEGER NOT NULL DEFAULT 0",
]

# User-defined lists (Bloco 12). Until now a list *was* its `list_type`
# string, so the set of lists was fixed by the `ListType` enum and a list had
# nowhere to keep a name or a creation date. This gives every list a row of
# its own and points `user_lists` at it.
#
# `slug` is what separates the two kinds of list. The predefined ones carry
# a `ListType` value ('blocked', 'library', 'want_to_play', ...) because code
# has to *reason* about them — Explorer hides blocked games, Library is
# resolved from installed ROMs rather than stored rows. Lists the user
# creates have `slug = NULL`: nothing but the user's own name identifies
# them, and no code branches on them.
#
# Why a table rather than just writing the name into `user_lists.list_type`:
# a user list called "blocked" would silently merge with the predefined one,
# and there would still be nowhere to store the name of a list that happens
# to be empty — it would vanish until something was added to it.
#
# NOTE: this originally left the v2 unique index `(account_id, game_id,
# list_type)` in place, calling it redundant. It wasn't — see
# `DROP_LEGACY_LIST_TYPE_INDEX_V17`, which removes it.
CREATE_TABLES_V15 = [
    """
    CREATE TABLE IF NOT EXISTS user_list_definitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        name TEXT NOT NULL,
        slug TEXT,
        is_predefined BOOLEAN NOT NULL DEFAULT 0,
        created_at DATETIME
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_list_definitions_account_name "
    "ON user_list_definitions(account_id, name)",
    "ALTER TABLE user_lists ADD COLUMN list_id INTEGER REFERENCES user_list_definitions(id)",
    # Same data migration the app would otherwise have to do lazily forever:
    # every list a user already had becomes a definition, and their existing
    # rows are pointed at it. Nothing is lost and nothing is renamed away
    # from them — the display names below are the ones the UI already showed.
    """
    INSERT OR IGNORE INTO user_list_definitions (account_id, name, slug, is_predefined, created_at)
    SELECT DISTINCT
        account_id,
        CASE list_type
            WHEN 'want_to_play' THEN 'Want to Play'
            WHEN 'playing' THEN 'Playing'
            WHEN 'completed' THEN 'Completed'
            WHEN 'abandoned' THEN 'Abandoned'
            WHEN 'blocked' THEN 'Blocked'
            ELSE list_type
        END,
        list_type,
        1,
        CURRENT_TIMESTAMP
    FROM user_lists
    """,
    """
    UPDATE user_lists
    SET list_id = (
        SELECT d.id FROM user_list_definitions d
        WHERE d.account_id = user_lists.account_id AND d.slug = user_lists.list_type
    )
    WHERE list_id IS NULL
    """,
    # Partial index: `list_id` is NULL only for rows the UPDATE above couldn't
    # resolve (an orphaned `list_type` with no matching definition), and a
    # plain unique index would treat every such NULL as distinct anyway.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_lists_account_game_list "
    "ON user_lists(account_id, game_id, list_id) WHERE list_id IS NOT NULL",
]

# Drops the predefined lists that v15 had just created, leaving Blocked as
# the only one the app ships. Decided with the user, who confirmed the four
# were empty on their account and preferred building their own from scratch
# with the new user-created lists.
#
# `Library` goes too, for a different reason: it stopped being a list and
# became its own page (`gui/pages/library_page.py`). It never behaved like a
# list — no stored rows, membership computed from `installed_roms`, and a
# layout nothing else shared.
#
# Membership rows are deleted first, not left orphaned: `user_lists.list_id`
# references `user_list_definitions`, so rows pointing at a deleted list
# would either break the foreign key or linger invisibly and reappear if an
# id were ever reused. This is a real deletion of data — safe here only
# because the lists were confirmed empty; the SQL is written to be correct
# regardless.
# Drops the v2 index `(account_id, game_id, list_type)`.
#
# v15 left it in place, reasoning it was redundant now that
# `(account_id, game_id, list_id)` enforces uniqueness. It was not: every
# user-created list writes the same `CUSTOM_LIST_TYPE_MARKER` into
# `list_type`, so that index read "a game may appear in at most one
# user-created list, ever". Putting the same game in two of your own lists
# raised `UNIQUE constraint failed: user_lists.account_id,
# user_lists.game_id, user_lists.list_type` — found by the test, not by
# reading the code.
#
# Its own version rather than an extra statement in v16, because a database
# that already ran v16 would never see it otherwise.
DROP_LEGACY_LIST_TYPE_INDEX_V17 = [
    "DROP INDEX IF EXISTS idx_user_lists_account_game_type",
]

# Per-account UI preferences: window state, cover sizes, anything else the
# user adjusts and expects to still be there next launch.
#
# A key/value table rather than a column per setting. These are view
# preferences with no relationships and no queries beyond "read mine" —
# adding a column (and a migration) for every slider would be a lot of
# schema churn for values nothing else ever joins against. `value` is TEXT
# and callers coerce; see `services/preferences_service.py`.
#
# Keyed by account because the app already supports switching accounts, and
# two people sharing a machine wanting the same cover size is a coincidence,
# not a rule.
# libretro core per console. RetroArch is one executable plus a core `.dll`
# per system, so "which emulator for this console" needs two paths, not one.
# Nullable: emulators with a real per-console binary don't have a core, and
# neither does an existing config, which keeps working untouched.
ALTER_TABLES_V19 = [
    "ALTER TABLE emulator_configs ADD COLUMN core_path TEXT",
]

# Tables left behind by Bloco 11, which deleted the Watch Folder organizer
# and the per-console Quick Links. Their models, repositories and UI all went
# then; only the tables stayed, on the reasoning that dropping them wasn't
# worth a destructive migration. Before shipping, an empty table nobody reads
# is just a thing the next person has to work out, so they go now.
#
# `CREATE_TABLES_V5`/`V6` still create them — they run before this on a fresh
# database and are left alone deliberately: rewriting shipped migrations
# would give existing and new databases different histories for no gain.
# Scopes ROM folders and installed ROMs to an account, like every other
# user-facing table already was. Two people sharing one install were seeing
# each other's library: `rom_folders` and `installed_roms` had no owner, so
# every query returned everything.
#
# Backfill assigns existing rows to the **active** account, falling back to
# the lowest account id. On a single-account install — every install so far —
# that is the only account, so nobody's library moves. `COALESCE` on the
# subqueries keeps the UPDATE valid on a database with no accounts at all
# (rows then stay NULL and belong to nobody, which is correct: there is no
# one to give them to).
ADD_ACCOUNT_SCOPE_V21 = [
    "ALTER TABLE rom_folders ADD COLUMN account_id INTEGER REFERENCES accounts(id)",
    "ALTER TABLE installed_roms ADD COLUMN account_id INTEGER REFERENCES accounts(id)",
    """
    UPDATE rom_folders SET account_id = COALESCE(
        (SELECT id FROM accounts WHERE is_active = 1 LIMIT 1),
        (SELECT MIN(id) FROM accounts)
    ) WHERE account_id IS NULL
    """,
    """
    UPDATE installed_roms SET account_id = COALESCE(
        (SELECT id FROM accounts WHERE is_active = 1 LIMIT 1),
        (SELECT MIN(id) FROM accounts)
    ) WHERE account_id IS NULL
    """,
    "CREATE INDEX IF NOT EXISTS idx_rom_folders_account ON rom_folders(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_installed_roms_account ON installed_roms(account_id)",
]

DROP_ORPHAN_TABLES_V20 = [
    "DROP TABLE IF EXISTS rom_destinations",
    "DROP TABLE IF EXISTS console_quick_links",
]

# Two more tables nothing ever read or wrote. Both were created by the
# original schema in anticipation of features that were never built:
#
#   notification_settings — per-account toggles for notification types. The
#       three repository methods that touched it had no callers and went with
#       the same cleanup round; `notifications` itself stays, it is live.
#   leaderboard_cache     — there is no leaderboard feature. Its repository
#       and model were deleted alongside this.
#
# Verified empty in both the source and the frozen-build databases before
# dropping. `IF EXISTS` because a database created after this migration
# landed still runs the historical CREATE statements above and then this —
# the same shape as V20, which is why those CREATEs are deliberately left
# alone: a migration list is a historical record, and editing an old entry
# desynchronises every database that already applied it.
DROP_ORPHAN_TABLES_V22 = [
    "DROP TABLE IF EXISTS notification_settings",
    "DROP TABLE IF EXISTS leaderboard_cache",
]

# RetroAchievements' API returns some games' hashes uppercase — 176 of 13327
# rows in one synced catalog, across 137 games including Pokémon Snap,
# Terranigma and Jet Force Gemini. Every hasher this app uses prints
# lowercase, and SQLite compares TEXT case-sensitively, so those games could
# never be matched: Pokémon Snap sat in "Unmatched ROMs" with a hash that was
# right in every character but its case.
#
# `find_game_id_by_hash` now compares with LOWER() on both sides so it works
# regardless, and `replace_hashes` lowercases on the way in. This normalizes
# the rows already stored, so that LOWER() on the column stops defeating
# `idx_game_hashes_hash` for everyone who synced before the fix.
NORMALIZE_GAME_HASH_CASE_V23 = [
    "UPDATE game_hashes SET hash = LOWER(hash) WHERE hash <> LOWER(hash)",
]

# Paths are unique per account. NULL owners need a separate index because
# SQLite normally allows repeated NULL values in a composite unique index.
SCOPE_LIBRARY_PATHS_V24 = [
    "DROP INDEX IF EXISTS idx_rom_folders_path",
    "DROP INDEX IF EXISTS idx_installed_roms_file_path",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rom_folders_account_path ON rom_folders(account_id, path)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rom_folders_unowned_path ON rom_folders(path) WHERE account_id IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_installed_roms_account_path ON installed_roms(account_id, file_path)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_installed_roms_unowned_path ON installed_roms(file_path) WHERE account_id IS NULL",
]

ADD_FLATPAK_CONFIG_V25 = [
    "ALTER TABLE emulator_configs ADD COLUMN flatpak_app_id TEXT",
    "ALTER TABLE emulator_configs ADD COLUMN flatpak_installation TEXT",
]

# R04: detect a ROM whose contents changed at an already-scanned path.
# `file_size`/`file_mtime_ns` are the fingerprint captured at hash time, so a
# rescan can tell "same file" from "different file now sitting at that path"
# without re-reading every byte. Nullable on purpose: rows written before this
# migration have no fingerprint, and a NULL forces a one-time rehash rather
# than being mistaken for a match. `manual_match` marks a `game_id` the user
# picked by hand, so a later hash-driven rematch never silently overrides it.
ADD_ROM_FINGERPRINT_V26 = [
    "ALTER TABLE installed_roms ADD COLUMN file_size INTEGER",
    "ALTER TABLE installed_roms ADD COLUMN file_mtime_ns INTEGER",
    "ALTER TABLE installed_roms ADD COLUMN manual_match BOOLEAN NOT NULL DEFAULT 0",
]

CREATE_TABLES_V18 = [
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        key TEXT NOT NULL,
        value TEXT,
        PRIMARY KEY (account_id, key)
    )
    """,
]

DELETE_DEFAULT_LISTS_V16 = [
    """
    DELETE FROM user_lists
    WHERE list_id IN (
        SELECT id FROM user_list_definitions
        WHERE is_predefined = 1
          AND slug IN ('library', 'want_to_play', 'playing', 'completed', 'abandoned')
    )
    """,
    """
    DELETE FROM user_list_definitions
    WHERE is_predefined = 1
      AND slug IN ('library', 'want_to_play', 'playing', 'completed', 'abandoned')
    """,
]
