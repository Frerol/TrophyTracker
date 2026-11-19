"""Console reference data (Database.md 2.2) — read path for GUI console pickers."""

from retrocheevos.database.connection import get_connection
from retrocheevos.core.console_reference import CONSOLE_NAMES, NON_EMULATOR_CONSOLE_IDS
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.models.console import Console


def list_consoles() -> list[Console]:
    with get_connection() as connection:
        return ConsoleRepository(connection).list_all()


def list_configurable_consoles() -> list[Console]:
    """Local configuration works before the first catalog sync, even offline.

    Keep this separate from the synced catalog: listing configuration options
    must not add unsupported consoles to the catalog synchronization queue.
    """
    consoles = {key: Console(id=key, name=name) for key, name in CONSOLE_NAMES.items()}
    consoles.update({console.id: console for console in list_consoles()})
    return sorted(
        (console for console in consoles.values() if console.id not in NON_EMULATOR_CONSOLE_IDS),
        key=lambda console: console.name.casefold(),
    )
