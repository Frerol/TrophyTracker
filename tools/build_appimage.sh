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

.venv/bin/pyinstaller --noconfirm Retrocheevos.spec
appdir="$PWD/build/Retrocheevos.AppDir"
mkdir -p "$appdir/usr"
# Replace the previous payload so removed dependencies do not linger.
.venv/bin/python - "$appdir" <<'PY'
import shutil
import sys
from pathlib import Path

appdir = Path(sys.argv[1])
target = appdir / "usr" / "Retrocheevos"
if target.exists():
    shutil.rmtree(target)
shutil.copytree("dist/Retrocheevos", target)
shutil.copy2("assets/icon.png", appdir / "retrocheevos.png")
PY
cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$APPDIR/usr/Retrocheevos/Retrocheevos" "$@"
EOF
chmod +x "$appdir/AppRun"
cat > "$appdir/retrocheevos.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Retrocheevos
Comment=RetroAchievements desktop companion
Exec=Retrocheevos
Icon=retrocheevos
Categories=Game;Utility;
Terminal=false
EOF
version="$(PYTHONPATH=src .venv/bin/python -c 'from retrocheevos.version import APP_VERSION; print(APP_VERSION)')"
ARCH=x86_64 "$tool" --no-appstream --runtime-file "$runtime" "$appdir" "dist/Retrocheevos-${version}-x86_64.AppImage"
