"""RetroCheevos entry point."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("Starting RetroCheevos")

    # Bring the schema up to date before any page touches the database.
    initialize_database().close()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
