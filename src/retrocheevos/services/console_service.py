"""Console reference data (Database.md 2.2) — read path for GUI console pickers."""

from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.models.console import Console


def list_consoles() -> list[Console]:
    with get_connection() as connection:
        return ConsoleRepository(connection).list_all()
