# Testing and continuous integration

TrophyTracker uses the standard-library `unittest` runner; there is no test
framework to install. GUI tests run on Qt's `offscreen` platform so they need
no display. All commands below run from the repository root with the project's
environment (`.venv`) active and `PYTHONPATH=src`.

## Commands

Run everything (core, services, database, library, GUI, packaging inputs):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

Run a subset, for example the GUI crash regressions only:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/gui -t .
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest tests.gui.test_lifecycle_regression
```

Run the reproducible performance probe (temporary data, mocked artwork, no
live API). Method and results are in
[PerformanceValidation.md](PerformanceValidation.md):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/benchmarks/benchmark_explorer.py
```

## Fresh environment

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.txt -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

`requirements-dev.txt` includes the locked release set plus development tools
(PyInstaller for the packaging smoke). Users need only `requirements.txt`.

Linux also needs the Qt runtime libraries the offscreen platform loads, for
example on Debian/Ubuntu:

```bash
sudo apt-get install -y --no-install-recommends \
  libegl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libglib2.0-0
```

## Continuous integration

[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) configures GitHub
Actions for pushes to `main`, pull requests, weekly runs and manual dispatch.
It requires a GitHub checkout/mirror with Actions enabled; Codeberg itself does
not execute `.github/workflows`. Local release validation below is separate
from hosted CI, which has not been run in this session.

| Job | Platforms | What it does |
| --- | --- | --- |
| `test` | `ubuntu-latest`, `windows-latest` × Python 3.12/3.13 | Installs `requirements.txt` + `requirements-dev.txt`, runs the full offscreen suite. |
| `packaging` | `ubuntu-latest`, `windows-latest` | Builds the frozen app with `pyinstaller packaging/TrophyTracker.spec`, then starts the bundle with `tools/checks/packaging_smoke.py` and verifies it initializes and creates its database. |
| `dependency-upgrade` | `ubuntu-latest`, `windows-latest` | Installs `requirements-upgrade.txt` over the release set and reruns the GUI suite, including fullscreen, navigation and worker-lifetime regressions. |

The packaging smoke probe launches the frozen executable with an isolated
per-user data directory and a bounded lifetime. A build that aborts during Qt or
database initialization exits early and fails the job; a healthy build keeps
running until the probe stops it. The probe also checks that
`logs/crash.log` stayed empty, which is the only artifact a native fault
leaves behind. `tests/test_packaging.py` covers the spec's inputs and bundle
contents without building.

The `dependency-upgrade` job is deliberately non-blocking
(`continue-on-error`): a broken newest PySide6 must not block releases pinned
to the reproducible set. It is the signal that decides whether the pin can be
raised.

## Dependency policy

Three files, three different jobs:

| File | Purpose |
| --- | --- |
| `requirements.txt` | Generated release lock with exact versions and SHA-256 hashes, including transitive and platform-specific dependencies. |
| `requirements-dev.txt` | Generated lock for release dependencies plus build tools (PyInstaller). |
| `requirements-upgrade.txt` | Deliberate upgrade probe. Installed over the release set only by CI. |

`requirements.txt` pins `PySide6==6.10.1` while the Explorer crash
investigation is being re-validated; the comment in `requirements.in` records why. Do not
raise that pin without running the upgrade probe first.

### Releasing a GUI/framework upgrade

1. Update `requirements-upgrade.txt` if the target is newer than its floor.
2. Run the `dependency-upgrade` job on Windows and Linux (CI, or locally:
   `.venv/bin/pip install --upgrade -r requirements-upgrade.txt`, then the
   GUI suite command above).
3. Confirm the fullscreen, navigation and worker-lifetime scenarios pass.
4. Only then change the `PySide6` pin in `requirements.in` and regenerate both lockfiles.

The upgrade probe is the regression check for the failure that motivated the
pin: a native `Qt6Widgets.dll` crash when entering fullscreen from Explorer.
`tests/gui/test_lifecycle_regression.py` repeats that scenario on every page,
including Home's embedded Explorer populated from an isolated SQLite database
with an active account, 40 matching games and completion data. It waits for
the asynchronous search, renders and scrolls the table across repeated
fullscreen transitions, and closes the window while a worker is
still running.

### Updating the lockfiles

Edit direct dependency policy in `requirements.in` / `requirements-dev.in`,
then regenerate with uv 0.13.9 (a maintainer tool, not a runtime dependency):

```bash
uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes -o requirements.txt
uv pip compile requirements-dev.in -c requirements.txt --universal --python-version 3.12 --generate-hashes -o requirements-dev.txt
```

Commit inputs and outputs together. Universal resolution preserves Windows
and Linux markers; both CI platforms install the same selected versions with
`--require-hashes`. This fixes Python package versions, not OS libraries or
bit-for-bit build output. The upgrade probe deliberately installs its Qt
candidate separately, without applying the release lock to that second step.

## R11/R12 validation — 2026-11-20

- Linux, Python 3.13, pinned PySide6 6.10.1: full suite, 298 tests passed.
- Windows Python 3.13 under Wine, pinned PySide6: 298 tests passed, including
  two expected POSIX symlink skips. Native Windows validation remains pending.
- Linux, Python 3.13, upgraded PySide6 6.12.0: all 61 GUI tests passed.
- Ubuntu 22.04 (glibc 2.35): the release AppImage and the frozen folder are
  checked with the startup probe, including database creation and empty crash
  log. The public 0.1.0 package targets Linux x86_64 only.

The platform run exposed Unix-only path assumptions in test fixtures and a
Windows sharing violation during concurrent atomic artwork publication. The
fixtures now use native paths/home variables; publication retries transient
Windows sharing/access failures with a bounded delay. Failure still preserves
the old cover and removes the temporary file.
