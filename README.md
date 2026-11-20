# TrophyTracker

Version **0.1.0**. The current release package targets Linux x86_64; Windows
builds remain experimental pending native Windows validation.

TrophyTracker is a desktop companion for [RetroAchievements](https://retroachievements.org) on Windows and Linux. It brings your local ROM library, achievement progress, account statistics and custom game lists into one place, with cover artwork and shortcuts to launch games through your configured emulators, including RetroArch.

**TrophyTracker is a fork of [RetroCheevos](https://github.com/Gmendes223/Retrocheevos), developed with the assistance of artificial intelligence (AI).** This fork builds on the original project's work and is being independently adapted and expanded with AI-assisted changes.

> **Note:** This project is not affiliated with, endorsed by, or in any way officially connected to RetroAchievements.org. It's a third-party tool built by a fan, using their public API.

---

## Project origin and compatibility

TrophyTracker preserves its origins as a fork of [RetroCheevos](https://github.com/Gmendes223/Retrocheevos); credit for the original application belongs to its author and contributors.
The Python package remains `retrocheevos`; existing data directories, database
filenames and credential-vault identifiers are retained for compatibility.
Run from source with `PYTHONPATH=src .venv/bin/python -m retrocheevos.main`.
Build Windows bundles with `pyinstaller packaging/TrophyTracker.spec`.

## What it is

An Android achievement-tracking companion is planned. See the
[Android roadmap](docs/planning/AndroidRoadmap.md) for scope, phases and release criteria.

TrophyTracker is a desktop app for Windows and Linux that connects to your RetroAchievements account to:

- Sync your game catalog, stats, and progress
- Organize your installed library in a "Library" view with clickable covers
- Create custom game lists (favorites, backlog, etc.)
- Block games you don't want showing up in search
- Track the recent activity of people you follow
- Launch games directly from the app, including support for multi-core emulators like RetroArch

## Getting started

1. Download and extract this release's `.zip` — **the whole folder**, not just the `.exe`.
2. Run `TrophyTracker.exe` from inside the extracted folder.
3. The first time you open it, no session is active — you'll need your RetroAchievements **API key**:
   - Log in at [retroachievements.org](https://retroachievements.org)
   - Go to your account control panel
   - Copy the "Web API Key"
4. Enter your username and API key in the app's Settings.
5. Run "Sync Everything" to sync the game catalog and your profile (this can take up to ~1h the first time, due to RetroAchievements' own API rate limits — that's normal, and it's resumable if interrupted).

## Per-account data

Each RetroAchievements account that signs in on this app has its own data stored locally on this PC (library, lists, stats, configured ROM folders). Logging out doesn't delete anything — signing back in with the same account brings everything back exactly as you left it.

## Setting up emulators

Console selection is available offline, before the first catalog sync.
Select a saved emulator to load its settings for editing.
Use **Find...** next to the executable field to search for known emulators
for the selected console. Search common installation locations or choose a
folder containing portable installations. Select a result, then click
**Save Emulator**. RetroArch also needs a core in the **Core** field.
On Linux, **Find...** also lists installed Flatpak emulators, including user
and system installations. Selecting one saves its application ID and launches
it through `flatpak run`. ROMs must be accessible under the Flatpak app's
filesystem permissions; RetroArch needs a core installed for its Flatpak version.
Console dropdowns show up to ten entries at a time and scroll through the rest.

In Settings, per console, configure:
- **Executable**: path to the emulator's `.exe`.
- **Core** (optional): if you use **RetroArch**, you also need to specify the core for that console (e.g. `snes9x_libretro.dll`). RetroArch doesn't have one exe per console — it uses a single exe with multiple cores.

## Repository organization

- `src/retrocheevos/`: application code, organized by layer.
- `tests/`: automated tests mirroring application modules.
- `docs/`: [documentation index](docs/README.md), technical reference, planning,
  design, validation and historical handoffs.
- `assets/`: runtime icon/logo; historical source art is under `assets/reference/`.
- `packaging/`: [build inputs and instructions](packaging/README.md).
- `tools/`: [checks, benchmarks and the optional RAHasher helper](tools/README.md).
- `.github/workflows/ci.yml`: CI for the full offscreen suite on Windows/Linux,
  packaging smoke builds and the deliberate dependency-upgrade probe.

Local `.venv/`, `database/`, `cache/`, `logs/`, `build/` and `dist/` directories
retain their existing purposes and are ignored by Git. Installed/frozen builds
continue using the existing per-user data paths.

Run tests from the repository root with the project's environment active:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

`requirements.txt` locks release dependencies and their hashes, including transitive packages; `requirements-dev.txt` locks the same set plus
development-only tools (PyInstaller), and `requirements-upgrade.txt` is the
deliberate upgrade probe CI installs over the release set. A fresh environment
only needs the first two:

```bash
.venv/bin/pip install --require-hashes -r requirements.txt -r requirements-dev.txt
```

Full command reference, CI jobs, the supported-platform matrix and the
dependency/upgrade policy are in
[docs/validation/Testing.md](docs/validation/Testing.md).

## Building an AppImage (Linux x86_64)

Create `.venv` with `python3 -m venv .venv`, then install dependencies with
`.venv/bin/pip install --require-hashes -r requirements.txt -r requirements-dev.txt`.
Download the official [appimagetool](https://github.com/AppImage/appimagetool/releases)
and [x86_64 runtime](https://github.com/AppImage/type2-runtime/releases).
Extract appimagetool with `--appimage-extract` if FUSE is unavailable, then run:

```sh
APPIMAGETOOL=/absolute/path/to/squashfs-root/AppRun \
APPIMAGE_RUNTIME=/absolute/path/to/runtime-x86_64 packaging/build_appimage.sh
```

The result is `dist/TrophyTracker-0.1.0-x86_64.AppImage` (version comes from
`src/retrocheevos/version.py`). Build on the oldest Linux distribution you
intend to support: AppImage does not bundle glibc. The Windows `RAHasher.exe`
is omitted; provide a native `tools/rahasher/RAHasher` with its license/source files
to bundle that optional helper, or use the app's built-in hashing.

## ROMs, artwork and live achievement tracking

Wii folders can contain RVZ files, including nested folders. RVZ/WIA disc
headers distinguish Wii from GameCube; a configured console is used when
the header does not identify it. `~` is expanded in folder paths.
These ROMs appear in the library even when no compatible achievement hash
can be computed. Use **Match to Game** when a catalog entry is available;
compressed-file MD5s are not used as substitutes for RetroAchievements hashes.

ROM thumbnails load automatically in Library and Home. User-picked covers
take priority, followed by nearby images (including `covers/` and `images/`),
Wii/GameCube covers identified by the disc ID, a **platform and game-name**
lookup in [Libretro Thumbnails](https://github.com/libretro-thumbnails), and
available RetroAchievements catalog artwork. Platform discovery and name
lookup work independently of an achievement match and include newly synced
console names. The index is cached for seven days and downloaded artwork
remains available offline. Wii/GameCube disc covers come from
[GameTDB](https://www.gametdb.com/).
If no published artwork is available, a console thumbnail is shown. Right-click
the ROM and choose **Choose cover…** to supply your own image.

Home's **Now Playing** panel follows locally launched games and recent
RetroAchievements activity. It refreshes achievement counts, points, locked
and unlocked achievements every minute while visible, highlights new unlocks,
and offers **Refresh progress**. Progress reflects updates published by
RetroAchievements; it does not read the emulator's memory. Network failures
keep the last result visible and back off retries.

## Sync buttons

| Button | Purpose |
| --- | --- |
| Sync Everything | Refresh consoles, the game catalog, your profile and event progress. |
| Sync ROM Hashes | Download identification hashes and recheck unmatched ROMs with compatible hashes. The optional detailed mode also fetches achievement definitions and median times. |
| Sync Median Times | Fill in median hardcore completion times for catalog games. Optional and potentially lengthy. |
| Sync Profile | Refresh your points, completion progress and awards. |

Artwork loads automatically when cards are displayed. Sync Everything does
not include the separate hash and median-time backfills.

## Updates

Automatic update checks are disabled for private TrophyTracker development. Install new builds manually; the app does not query the original project for updates.

## Known limitations

- The RetroAchievements API has per-minute/hour rate limits. Large syncs (first-time sync, median times) can take a while and, rarely, fail from too many requests — if that happens, wait a few minutes and try again; progress already made isn't lost.
- This app doesn't distribute or download ROMs — it only points to local folders you already have.

## Support

This is a personal/hobby project. If you run into a bug, [open an issue](../../issues) on this repository.
