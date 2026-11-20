#!/usr/bin/env bash
# Run after installing requirements.txt and PyInstaller in .venv.
set -euo pipefail
cd "$(dirname "$0")/.."

tool="${APPIMAGETOOL:-$PWD/build/appimage-tools/squashfs-root/AppRun}"
runtime="${APPIMAGE_RUNTIME:-$PWD/build/appimage-tools/runtime-x86_64}"
if [[ ! -x "$tool" || ! -f "$runtime" ]]; then
    echo "Set APPIMAGETOOL and APPIMAGE_RUNTIME to locally downloaded AppImage tools." >&2
    exit 1
fi

.venv/bin/pyinstaller --noconfirm TrophyTracker.spec
appdir="$PWD/build/TrophyTracker.AppDir"
mkdir -p "$appdir/usr"
# Replace the previous payload so removed dependencies do not linger.
.venv/bin/python - "$appdir" <<'PY'
import shutil
import sys
from pathlib import Path

appdir = Path(sys.argv[1])
target = appdir / "usr" / "TrophyTracker"
if target.exists():
    shutil.rmtree(target)
shutil.copytree("dist/TrophyTracker", target)
shutil.copy2("assets/icon.png", appdir / "trophytracker.png")
PY
cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$APPDIR/usr/TrophyTracker/TrophyTracker" "$@"
EOF
chmod +x "$appdir/AppRun"
cat > "$appdir/trophytracker.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=TrophyTracker
Comment=RetroAchievements desktop companion
Exec=TrophyTracker
Icon=trophytracker
Categories=Game;Utility;
Terminal=false
EOF
version="$(PYTHONPATH=src .venv/bin/python -c 'from retrocheevos.version import APP_VERSION; print(APP_VERSION)')"
output="dist/TrophyTracker-${version}-x86_64.AppImage"
temporary_output="${output%.AppImage}.build-$$.AppImage"
trap 'rm -f -- "$temporary_output"' EXIT
ARCH=x86_64 "$tool" --no-appstream --runtime-file "$runtime" "$appdir" "$temporary_output"
# Replace atomically: an older AppImage may currently be mounted/running.
mv -f -- "$temporary_output" "$output"
