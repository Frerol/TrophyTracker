# Packaging

Run build commands from the repository root. Build output remains in `build/`
and `dist/`, which are ignored by Git. See the [project README](../README.md)
for dependency installation and AppImage tool setup.

Windows (experimental; validate on native Windows before publishing):

```powershell
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe packaging/build_windows.py
```

Linux:

```bash
.venv/bin/python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
APPIMAGETOOL=/absolute/path/to/squashfs-root/AppRun \
APPIMAGE_RUNTIME=/absolute/path/to/runtime-x86_64 packaging/build_appimage.sh
```

The spec resolves source, artwork and helper paths relative to the repository,
independently of the caller's working directory. PyInstaller's default output
paths are relative to the caller, so using the repository root keeps artifacts
in the standard directories. The AppImage script changes to that root itself.

Only `assets/icon.png` and `assets/logo.png` are bundled as runtime artwork.
Design proposals, historical reference art and local account data are excluded.
The optional native RAHasher helper is bundled from `tools/rahasher/` only when
its executable and both license/source notice files are present together.

The Windows helper builds into `dist/windows/TrophyTracker/`, runs the
initialization smoke probe, then creates
`dist/TrophyTracker-0.1.0-windows-x86_64-portable.zip`. Extract the entire
folder and run `TrophyTracker.exe`; `_internal/` must stay next to it.
No installer is needed; user data still lives under `%LOCALAPPDATA%\Retrocheevos`.
Wine builds are useful for checking packaging but do not replace native Windows
validation. The 0.1.0 release is Linux only.

Build the Linux release on Ubuntu 22.04 (glibc 2.35) or the oldest target
platform. `PYTHON=/path/to/python` selects another build environment instead
of `.venv/bin/python`. Install both locks in that environment first. Smoke-test
both the folder and final AppImage:

```bash
.venv/bin/python tools/checks/packaging_smoke.py dist/TrophyTracker/TrophyTracker
APPIMAGE_EXTRACT_AND_RUN=1 .venv/bin/python tools/checks/packaging_smoke.py dist/TrophyTracker-0.1.0-x86_64.AppImage
```

The extraction option works without FUSE. For normal use mark the AppImage
executable (`chmod +x TrophyTracker-0.1.0-x86_64.AppImage`) and launch it.
The Linux build omits the Windows-only RAHasher helper.

The canonical English release notes are tracked in `packaging/RELEASE-0.1.0.txt`.
Copy them to `dist/release/RELEASE-0.1.0.txt` when preparing the release, and
regenerate `SHA256SUMS` whenever release documentation changes.

For Codeberg, attach the AppImage, `SHA256SUMS` and the prepared release notes
from `dist/release/` to tag `v0.1.0`. Generated binaries remain outside Git.
