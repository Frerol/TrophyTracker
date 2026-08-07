"""Application-wide logging configuration."""

import logging
from logging.handlers import RotatingFileHandler

from retrocheevos.database.connection import default_data_dir

# Alongside the database, for the same reasons (`database/connection.py`):
# a frozen build must not write next to the executable — that path is either
# a temp extraction directory or a location the user can't write to — and
# logs record what *this* person did, so they belong under their profile.
LOG_DIR = default_data_dir() / "logs"
LOG_FILE = LOG_DIR / "retrocheevos.log"

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with console and rotating file handlers.

    Must be called once, on startup, before any other module logs.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
