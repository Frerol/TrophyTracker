"""Retrocheevos entry point."""

import faulthandler
import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.pages.home_page import ICON_PATH
from retrocheevos.gui.styles import APP_STYLESHEET
from retrocheevos.utils.logging_setup import LOG_DIR, configure_logging

logger = logging.getLogger(__name__)

CRASH_LOG_FILE = LOG_DIR / "crash.log"
# Windows groups taskbar icons/entries by "Application User Model ID" —
# without setting one explicitly, a python.exe-hosted app is grouped under
# python.exe itself and can show *its* icon in the taskbar, no matter what
# `setWindowIcon` is called with (`QIcon(LOGO_PATH)` was confirmed to load
# correctly — not the icon file/path at fault). Must be set before the
# first window is shown.
APP_USER_MODEL_ID = "Retrocheevos.App"

# `icon.png` is a single 889x889 image. Handing Qt one oversized pixmap
# leaves it to downscale on demand for every slot Windows asks for (16px in
# the title bar, 32px in the taskbar, 256px in Alt-Tab), which is where a
# large source image tends to come out muddy or, on some shells, not at all.
# Pre-scaling into the icon gives each slot a purpose-made bitmap.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


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
        icon.addPixmap(
            source.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    logger.info(
        "Loaded app icon from %s (%dx%d source, %d sizes, AUMID %s)",
        ICON_PATH,
        source.width(),
        source.height(),
        len(ICON_SIZES),
        APP_USER_MODEL_ID,
    )
    return icon


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
    logger.info("Starting Retrocheevos")

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)

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

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    # Belt-and-suspenders with `MainWindow.setWindowIcon`: the app-level
    # icon is what some Windows UI (Alt-Tab, taskbar) reads directly,
    # rather than falling back to the per-window one.
    app_icon = _build_app_icon()
    app.setWindowIcon(app_icon)
    window = MainWindow()
    window.setWindowIcon(app_icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
