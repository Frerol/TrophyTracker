r"""Build and smoke-test a Windows portable ZIP using the current Python.

Run on Windows: .venv\Scripts\python.exe packaging/build_windows.py
The ZIP contains TrophyTracker.exe and its required _internal directory.
"""

from pathlib import Path
import shutil
import subprocess
import sys


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Run this script with Windows Python.")
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "src"))
    from retrocheevos.version import APP_VERSION

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", "dist/windows", "--workpath", "build/windows",
         "packaging/TrophyTracker.spec"],
        cwd=root, check=True,
    )
    subprocess.run(
        [sys.executable, "tools/checks/packaging_smoke.py",
         str(root / "dist/windows/TrophyTracker/TrophyTracker.exe")],
        cwd=root, check=True,
    )
    archive = shutil.make_archive(
        str(root / "dist" / f"TrophyTracker-{APP_VERSION}-windows-x86_64-portable"),
        "zip", root_dir=root / "dist/windows", base_dir="TrophyTracker",
    )
    print(f"Portable release: {archive}")


if __name__ == "__main__":
    main()
