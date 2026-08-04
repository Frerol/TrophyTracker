"""SQLite DDL statements for the RetroCheevos schema (Database.md).

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
