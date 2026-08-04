"""RetroCheevos entry point."""

import faulthandler
import logging
import sys

from PySide6.QtWidgets import QApplication

from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.styles import SCROLLBAR_STYLESHEET
from retrocheevos.utils.logging_setup import LOG_DIR, configure_logging

logger = logging.getLogger(__name__)

CRASH_LOG_FILE = LOG_DIR / "crash.log"


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
    logger.info("Starting RetroCheevos")

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
    app.setStyleSheet(SCROLLBAR_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
