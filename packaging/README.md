# Packaging

Run build commands from the repository root. Build output remains in `build/`
and `dist/`, which are ignored by Git. See the [project README](../README.md)
for dependency installation and AppImage tool setup.

Windows:

```powershell
.venv\Scripts\pyinstaller.exe packaging/TrophyTracker.spec
```

Linux:

```bash
.venv/bin/pyinstaller packaging/TrophyTracker.spec
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
