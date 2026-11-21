"""TrophyTracker entry point."""

import ctypes
import ctypes.wintypes
import faulthandler
import logging
import sys
import time

from PySide6.QtCore import QAbstractNativeEventFilter, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.assets import assets_dir as _assets_dir
from retrocheevos.gui.assets import ICON_PATH
from retrocheevos.gui.styles import apply_theme
from retrocheevos.services import credential_store
from retrocheevos.utils.logging_setup import LOG_DIR, configure_logging

logger = logging.getLogger(__name__)

CRASH_LOG_FILE = LOG_DIR / "crash.log"
# Windows groups taskbar icons/entries by "Application User Model ID" —
# without setting one explicitly, a python.exe-hosted app is grouped under
# python.exe itself and can show *its* icon in the taskbar, no matter what
# `setWindowIcon` is called with (`QIcon(LOGO_PATH)` was confirmed to load
# correctly — not the icon file/path at fault). Must be set before the
# first window is shown.
#
# The `.v2` suffix is load-bearing — see `_set_windows_app_id`. Changing this
# string again resets the shell's association for the app, which is a real
# effect on users' machines (taskbar pins stop resolving), so do not edit it
# to tidy up naming.
APP_USER_MODEL_ID = "TrophyTracker.App.v2"

# `icon.png` is a single 889x889 image. Handing Qt one oversized pixmap
# leaves it to downscale on demand for every slot Windows asks for (16px in
# the title bar, 32px in the taskbar, 256px in Alt-Tab), which is where a
# large source image tends to come out muddy or, on some shells, not at all.
# Pre-scaling into the icon gives each slot a purpose-made bitmap.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

_WM_GETICON = 0x007F


class _MSG(ctypes.Structure):
    """The Win32 `MSG` a Qt native event hands over as an opaque address."""

    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]


def _build_app_icon() -> QIcon:
    """The one place an app icon is built. `MainWindow` used to build its own
    single-pixmap `QIcon(ICON_PATH)` as well, which briefly won before this
    one replaced it — two icons racing for the same window is exactly the
    shape of an "appears sometimes" bug, so there is now only one.

    Logged unconditionally: taskbar-icon reports have come back twice with
    nothing reproducible, and without a line in `logs/` saying whether the
    file loaded and at which sizes, the next report is just as unfalsifiable
    as the last two.
    """
    source = QPixmap(str(ICON_PATH))
    icon = QIcon()
    if source.isNull():
        logger.warning("Application icon missing or unreadable: %s", ICON_PATH)
        return icon
    for size in ICON_SIZES:
        # Pixel-exact renders (with the tighter 16/24 px variant) when bundled;
        # otherwise resample the single large icon.
        sized = QPixmap(str(_assets_dir() / "icons" / f"trophytracker-{size}.png"))
        if sized.isNull() or sized.width() != size:
            sized = source.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        icon.addPixmap(sized)
    # Both the AUMID and whether this is a frozen run are logged, because the
    # taskbar bug turned on exactly that pair and a log that only said
    # "AUMID TrophyTracker.App" on every run is part of why it was chased
    # through the icon file for so long. See `_set_windows_app_id`.
    logger.info(
        "Loaded app icon from %s (%dx%d source, %d sizes, frozen=%s, AUMID %s)",
        ICON_PATH,
        source.width(),
        source.height(),
        len(ICON_SIZES),
        bool(getattr(sys, "frozen", False)),
        APP_USER_MODEL_ID if sys.platform == "win32" else "n/a (not Windows)",
    )
    return icon


def _set_windows_app_id() -> None:
    """Claim a taskbar identity, from source and frozen alike.

    An explicit AppUserModelID is how a python.exe-hosted app stops being
    grouped under python.exe, so running from source has always needed one.
    Frozen, it should be unnecessary — the process *is* `TrophyTracker.exe`,
    which the shell can hang an identity on by itself — and for a while this
    function returned early in that case.

    That turned out not to hold, and the way it failed is worth recording so
    nobody removes this again on the same reasoning:

    * With no explicit ID, the frozen app's taskbar button rendered the
      correct icon most of the time and the generic white placeholder some of
      the time, on the same build, minutes apart. Verified by screenshot on
      both sides of the transition.
    * The app was not at fault in either state. `WM_GETICON` returned live
      `ICON_BIG`/`ICON_SMALL` handles with the right artwork throughout,
      unchanged across six minutes of polling; the window was visible,
      unowned, uncloaked and taskbar-eligible; the icon compiled into the
      .exe probed clean at all ten sizes the shell asks for; and the message
      loop never once failed to answer within the shell's timeout.

    So the varying part is how the shell resolves *which application* the
    window belongs to. Deriving that from the executable path leaves it free
    to consult a cache that still remembers this path under the previous ID
    — the original app declared `Retrocheevos.App` before — and that stale association
    is the remaining explanation for an intermittent placeholder.

    Hence `.v2`: an identifier the shell has never seen, so nothing cached
    can answer for it. That is why this is set unconditionally now, and why
    the suffix must not be tidied away. Whether it fixes the intermittency is
    the open question this exists to answer.
    """
    if sys.platform != "win32":
        return

    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


class _IconQueryLogger(QAbstractNativeEventFilter):
    """Logs every `WM_GETICON` the shell sends this app's windows.

    Diagnostic, and deliberately kept: the taskbar-icon bug has now been
    chased twice through black-box observation — screenshots, icon probes,
    responsiveness polling — and every one of those measures the app *after*
    the shell has already made its decision. What none of them can see is the
    only moment that matters: whether the shell asked for the icon at all,
    and when relative to the event loop starting.

    One line per query, and the shell sends a handful per window, so this
    costs nothing in a log that already carries a line per synced game.

    `wParam` is the size class asked for: 0 `ICON_SMALL`, 1 `ICON_BIG`,
    2 `ICON_SMALL2`. `handled=False` always — this only observes; Qt's own
    window procedure still answers.
    """

    def __init__(self) -> None:
        super().__init__()
        self._started = time.monotonic()
        self._count = 0

    def nativeEventFilter(self, event_type, message):  # type: ignore[override]
        if event_type == b"windows_generic_MSG":
            msg = _MSG.from_address(int(message))
            if msg.message == _WM_GETICON:
                self._count += 1
                logger.info(
                    "WM_GETICON #%d: hwnd=%#x wParam=%d at +%.3fs after loop start",
                    self._count,
                    msg.hwnd or 0,
                    msg.wParam,
                    time.monotonic() - self._started,
                )
        return False, 0


def _log_uncaught_exception(exc_type, exc_value, exc_tb) -> None:
    """PySide6's default excepthook prints straight to stderr, bypassing
    `logging` entirely — an exception raised inside a Qt slot (e.g. from a
    signal callback) would otherwise never reach `logs/retrocheevos.log`,
    the opposite of every other error path in this app.
    """
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))


def main() -> int:
    configure_logging()
    sys.excepthook = _log_uncaught_exception
    logger.info("Starting TrophyTracker")

    _set_windows_app_id()

    # `sys.excepthook` only ever sees Python exceptions — a genuine native
    # crash (e.g. a Qt/GUI object touched off the main thread) never reaches
    # it and leaves nothing in `logs/retrocheevos.log`. `faulthandler` hooks
    # the OS-level fault signal itself and dumps whichever Python frame was
    # executing at the moment of the crash — the only way to get a usable
    # traceback out of that class of failure. Left open deliberately: this
    # file needs to survive the abnormal process exit that's about to happen.
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    crash_log = open(CRASH_LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115
    faulthandler.enable(file=crash_log)

    # Bring the schema up to date before any page touches the database.
    initialize_database().close()

    # After the schema, before any page reads an account: moves API keys out
    # of the plaintext column and into the OS credential vault. Idempotent —
    # once moved there is nothing left to find.
    try:
        credential_store.migrate_plaintext_keys()
    except Exception:
        logging.getLogger(__name__).warning(
            "Credential reconciliation deferred; database fallback retained"
        )
    # Retry any OS-vault deletions that could not be completed earlier (for
    # example because the vault was temporarily unavailable). Best effort.
    try:
        from retrocheevos.services import session_service
        session_service.cleanup_pending_credentials()
    except Exception:  # noqa: BLE001
        pass

    app = QApplication(sys.argv)
    # Installed before any window exists, so the very first query is caught.
    # Held on `app` rather than a local: Qt keeps only a borrowed pointer, and
    # a filter garbage-collected mid-run would take the app down with it.
    if sys.platform == "win32":
        app._icon_query_logger = _IconQueryLogger()  # type: ignore[attr-defined]
        app.installNativeEventFilter(app._icon_query_logger)  # type: ignore[attr-defined]
    apply_theme(app)
    # Belt-and-suspenders with `MainWindow.setWindowIcon`: the app-level
    # icon is what some Windows UI (Alt-Tab, taskbar) reads directly,
    # rather than falling back to the per-window one.
    app_icon = _build_app_icon()
    app.setWindowIcon(app_icon)
    window = MainWindow()
    window.setWindowIcon(app_icon)
    window.show()
    _reassert_window_icon(window, app_icon)
    return app.exec()


def _reassert_window_icon(window: MainWindow, app_icon: QIcon) -> None:
    """Set the window icon again, from inside the running event loop.

    `show()` is what makes the shell create the taskbar button, and the shell
    asks the new window for its icon almost immediately — but `show()` runs
    *before* `app.exec()`, so at that moment nothing in this process is
    pumping messages yet. `WM_GETICON` is a **sent** message: answering it
    requires the target thread to be in a message loop. A query that lands in
    that gap goes unanswered until it times out, and the shell keeps the
    generic placeholder it started the button with.

    That gap is normally microseconds, which is exactly why the symptom was
    intermittent — the taskbar button showed the right icon most of the time,
    and a plain white rectangle when the timing went the wrong way, on the
    same build minutes apart. It also explains why every measurement of the
    app itself came back clean: by the time anything could be inspected, the
    loop was running and `WM_GETICON` answered correctly forever after. The
    window was never wrong; only the shell's one-shot first look at it was.

    Re-setting the icon once the loop is up sends a fresh `WM_SETICON`, which
    is the documented way to make the shell re-read a taskbar button's icon.
    Queued at 0ms and again at 1500ms: the first covers the ordinary case,
    the second the secondary-monitor taskbars, which build their buttons on a
    separate and later pass — and the vertical monitor's taskbar is where
    this was actually seen.
    """
    def reassert() -> None:
        window.setWindowIcon(app_icon)

    QTimer.singleShot(0, reassert)
    QTimer.singleShot(1500, reassert)


if __name__ == "__main__":
    sys.exit(main())
