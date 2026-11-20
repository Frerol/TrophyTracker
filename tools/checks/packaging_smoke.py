"""Start a frozen TrophyTracker build long enough to prove it initializes.

CI runs this after `pyinstaller packaging/TrophyTracker.spec` on Windows and
Linux. The probe launches the bundle with an isolated per-user data directory
and a bounded lifetime:

* a build that aborts during Qt or database initialization exits early, which
  the probe reports together with whatever the bundle wrote to stdout/stderr;
* a healthy GUI keeps running until the probe stops it, and is expected to
  have created the per-user database.

The frozen app has no CLI mode, so "still alive after N seconds" is the only
portable liveness signal. A native fault would additionally leave a non-empty
``logs/crash.log``, which is checked.

Usage::

    python tools/checks/packaging_smoke.py dist/TrophyTracker/TrophyTracker

Exit status is 0 when the build starts, 1 when it does not, and 2 for a usage
or environment error.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

# Long enough for Qt, the migration runner and the first page construction,
# including a cold filesystem. Short enough to keep CI affordable.
STARTUP_SECONDS = 20.0
POLL_INTERVAL_SECONDS = 0.25
# A retry without QT_QPA_PLATFORM only matters on hosts whose Qt build has no
# offscreen plugin; anything this fast was a startup abort, not a slow boot.
PLATFORM_RETRY_SECONDS = 2.0

APP_DIR_NAME = "Retrocheevos"


def _isolated_environment(root: Path, offscreen: bool) -> dict[str, str]:
    """Copy the environment with per-user data roots redirected into `root`."""
    env = os.environ.copy()
    home = root / "home"
    xdg = root / "xdg"
    home.mkdir(parents=True, exist_ok=True)
    xdg.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(xdg)
    if sys.platform == "win32":
        local_app_data = root / "localappdata"
        local_app_data.mkdir(parents=True, exist_ok=True)
        env["LOCALAPPDATA"] = str(local_app_data)
    if offscreen:
        env["QT_QPA_PLATFORM"] = "offscreen"
    else:
        env.pop("QT_QPA_PLATFORM", None)
    return env


def _data_dir(env: dict[str, str]) -> Path:
    base = env.get("LOCALAPPDATA") or env.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path(env["HOME"]) / f".{APP_DIR_NAME.lower()}"


def _crash_log(env: dict[str, str]) -> Path:
    return _data_dir(env) / "logs" / "crash.log"


def _run(executable: Path, env: dict[str, str], log_path: Path) -> tuple[int, float]:
    """Launch the bundle and return (early_exit_status, seconds_survived).

    A status of ``None`` means the bundle was still running when the lifetime
    budget expired and the probe stopped it.
    """
    with log_path.open("ab") as log:
        process = subprocess.Popen([str(executable)], env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + STARTUP_SECONDS
        while time.monotonic() < deadline:
            status = process.poll()
            if status is not None:
                return status, time.monotonic() - (deadline - STARTUP_SECONDS)
            time.sleep(POLL_INTERVAL_SECONDS)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return None, STARTUP_SECONDS


def _report_log_tail(log_path: Path) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-20:])


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: packaging_smoke.py <path-to-TrophyTracker-executable>", file=sys.stderr)
        return 2
    executable = Path(argv[1])
    if not executable.is_file():
        print(f"missing build: {executable}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        attempts = [("offscreen", True)]
        if sys.platform == "win32":
            # Windows runners sometimes lack a usable desktop session; the
            # offscreen plugin is tried first, then a plain launch.
            attempts.append(("desktop", False))
        else:
            attempts = [("offscreen", True)]

        for label, offscreen in attempts:
            env = _isolated_environment(root / label, offscreen)
            log_path = root / f"{label}.log"
            status, survived = _run(executable, env, log_path)
            if status is None:
                crash_log = _crash_log(env)
                if crash_log.is_file() and crash_log.stat().st_size > 0:
                    print(f"crash log written during {label} run:\n{_report_log_tail(crash_log)}", file=sys.stderr)
                    return 1
                database = _data_dir(env) / "database" / "retrocheevos.db"
                if not database.is_file():
                    print(
                        f"bundle ran on the {label} platform but did not create {database}",
                        file=sys.stderr,
                    )
                    return 1
                print(f"bundle started ({label} platform) and created its database")
                return 0
            print(
                f"bundle exited early on the {label} platform with status {status} "
                f"after {survived:.2f}s",
                file=sys.stderr,
            )
            tail = _report_log_tail(log_path)
            if tail:
                print(tail, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
