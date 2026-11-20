# TrophyTracker — Architecture

## 1. Technology Stack

- **Language:** Python
- **GUI Framework:** PySide6 (Qt)
- **Database:** SQLite
- **HTTP:** Requests
- **HTML Parsing:** BeautifulSoup (only if strictly necessary — see `API.md`)
- **Images:** Pillow
- **Version Control:** Git / GitHub
- **Implementation Assistant:** Claude Code

## 2. Layered Architecture

Strict one-directional dependency flow:

```
GUI
 ↓
Services
 ↓
Core
 ↓
Database
 ↓
API
 ↓
Library
```

**Hard rule: GUI must never communicate directly with the API.**
All API access goes through `Services` → `Core`. This keeps the UI layer
swappable (see Section 6, Steam Deck / Linux support) and keeps business
logic testable without a running UI.

### 2.1 Layer Responsibilities

- **GUI** — PySide6 widgets, views, navigation. Renders state, forwards user
  actions to Services. Contains no business logic and no direct DB/API calls.
- **Services** — Orchestration layer. Coordinates Core + Database + API calls
  for a given use case (e.g. "refresh library", "switch account", "apply
  filters"). This is what the GUI talks to.
- **Core** — Business logic and domain rules (e.g. what counts as
  "Completed", how Median Time to Beat is computed/cached, ROM-hash matching rules,
  recommendation logic). No PySide6 imports here.
- **Database** — SQLite access layer: schema, migrations, queries, caching
  logic. No business rules here, only persistence. See `Database.md`.
- **API** — RetroAchievements API client. Handles authentication, requests,
  rate limiting, response parsing into raw data structures. See `API.md`.
- **Library** — ROM scanning, hashing, and local file organization
  (Watch Folder logic, console folder structure, install status detection).

## 3. Folder Structure

```
TrophyTracker/
├── assets/                  # Runtime icon.png and logo.png
│   └── reference/           # Historical source artwork (not bundled)
├── docs/
│   ├── README.md            # Documentation index
│   ├── Architecture.md      # Technical references remain directly in docs/
│   ├── API.md
│   ├── Database.md
│   ├── CodingStandards.md
│   ├── planning/            # Desktop/Android roadmaps, vision and ideas
│   ├── design/              # UI/branding specs, HTML proposal and previews
│   ├── validation/          # Performance and resilience evidence
│   └── archive/             # Historical implementation handoffs
├── packaging/               # PyInstaller spec and AppImage build script
├── tools/
│   ├── benchmarks/          # Repeatable development probes
│   └── rahasher/            # Optional binary and license/source notices
├── src/
│   └── retrocheevos/
│       ├── api/
│       ├── core/
│       ├── database/
│       ├── gui/
│       ├── library/
│       ├── models/
│       ├── services/
│       ├── utils/
│       ├── widgets/
│       └── main.py
├── tests/                   # Mirrors the source layers
├── README.md
├── CHANGELOG.md
└── requirements.txt
```

Local `.venv/`, `database/`, `cache/`, `logs/`, `exports/`, `build/` and `dist/`
are generated or user-specific and remain ignored. This organization does not
change runtime data locations. Use the [documentation index](README.md) to find
specifications; build commands are in [packaging](../packaging/README.md).


### 3.1 `src/retrocheevos/` Module Guide

- `api/` — RetroAchievements API client(s), request/response models,
  authentication.
- `core/` — Domain logic: filtering rules, median-time-to-beat logic, ROM
  compatibility rules, recommendation engine, notification rules.
- `database/` — SQLite connection management, schema/migrations, DAOs/
  repositories, cache invalidation.
- `gui/` — PySide6 windows, pages (Home, Library, Leaderboards, Lists,
  Settings, plus the Explorer embedded inside Home) and their view logic
  only.
- `library/` — ROM scanner, hasher, Watch Folder daemon, console-folder
  organizer, emulator process launching.
- `models/` — Shared data classes/DTOs used across layers (Game, Account,
  Achievement, ListEntry, etc.), fully type-hinted.
- `services/` — Use-case orchestration consumed by `gui/`.
- `utils/` — Generic helpers (logging setup, formatting, threading helpers).
- `widgets/` — Reusable custom Qt widgets (Game Card, Filter Bar, etc.),
  presentation-only.
- `main.py` — Application entry point.

## 4. Threading & Caching

- All long-running work runs off the UI thread — see `CodingStandards.md`
  for the threading rules.
- SQLite is the offline-friendly local cache for everything — see
  `Database.md` for schema and cache-refresh rules, and `API.md` for the
  request policy that feeds it.

## 5. Future Platform Support (Linux / Steam Deck)

- Business logic (`core/`, `services/`, `database/`, `api/`, `library/`)
  must remain platform-agnostic.
- Only `gui/` (and platform-specific parts of `library/` for file paths)
  should require adaptation for Linux/Steam Deck.
- No Windows-specific assumptions should leak outside the GUI/Library
  platform-adapter boundary.

## 6. Non-Goals

- No direct GUI → API calls, ever.
- No scraping unless strictly unavoidable, and never as a substitute for the
  RetroAchievements API for Median Time to Beat data.
- No blocking calls on the UI thread.
