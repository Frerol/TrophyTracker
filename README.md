# Retrocheevos

A desktop companion for [RetroAchievements](https://retroachievements.org), for organizing your ROM library, tracking your progress, and launching games directly from the app.

> **Note:** This project is not affiliated with, endorsed by, or in any way officially connected to RetroAchievements.org. It's a third-party tool built by a fan, using their public API.

---

## What it is

Retrocheevos is a Windows desktop app that connects to your RetroAchievements account to:

- Sync your game catalog, stats, and progress
- Organize your installed library in a "Library" view with clickable covers
- Create custom game lists (favorites, backlog, etc.)
- Block games you don't want showing up in search
- Track the recent activity of people you follow
- Launch games directly from the app, including support for multi-core emulators like RetroArch

## Getting started

1. Download and extract this release's `.zip` — **the whole folder**, not just the `.exe`.
2. Run `Retrocheevos.exe` from inside the extracted folder.
3. The first time you open it, no session is active — you'll need your RetroAchievements **API key**:
   - Log in at [retroachievements.org](https://retroachievements.org)
   - Go to your account control panel
   - Copy the "Web API Key"
4. Enter your username and API key in the app's Settings.
5. Run "Sync Everything" to sync the game catalog and your profile (this can take up to ~1h the first time, due to RetroAchievements' own API rate limits — that's normal, and it's resumable if interrupted).

## Per-account data

Each RetroAchievements account that signs in on this app has its own data stored locally on this PC (library, lists, stats, configured ROM folders). Logging out doesn't delete anything — signing back in with the same account brings everything back exactly as you left it.

## Setting up emulators

In Settings, per console, configure:
- **Executable**: path to the emulator's `.exe`.
- **Core** (optional): if you use **RetroArch**, you also need to specify the core for that console (e.g. `snes9x_libretro.dll`). RetroArch doesn't have one exe per console — it uses a single exe with multiple cores.

## Updates

The app automatically checks whether a newer version has been published on GitHub and shows a small notice — it never downloads or installs anything on its own. You'll need to manually grab the new version when you want to update.

## Known limitations

- The RetroAchievements API has per-minute/hour rate limits. Large syncs (first-time sync, median times) can take a while and, rarely, fail from too many requests — if that happens, wait a few minutes and try again; progress already made isn't lost.
- This app doesn't distribute or download ROMs — it only points to local folders you already have.

## Support

This is a personal/hobby project. If you run into a bug, [open an issue](../../issues) on this repository.
