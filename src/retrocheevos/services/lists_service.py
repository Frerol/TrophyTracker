"""List management (UI.md 3.6, Database.md §4.1)."""

from datetime import datetime
from typing import Optional

from retrocheevos.core.lists import (
    PREDEFINED_LISTS,
    validate_new_list_name,
)
from retrocheevos.core.lists import get_games_in_list as _get_games_in_list
from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.models.list_definition import ListDefinition
from retrocheevos.models.list_entry import ListEntry


def ensure_predefined_lists(account_id: int) -> list[ListDefinition]:
    """Create any missing predefined list for this account and return every
    list it has.

    Called before anything reads lists, rather than at account creation: the
    v15 migration converts lists that already had rows, but an account with
    no list entries at all — a fresh one, or one that never used lists — would
    otherwise end up with nothing, including no Blocked list for Explorer to
    filter against. Doing it on read means it also self-heals if a predefined
    list is ever deleted.
    """
    with get_connection() as connection:
        repository = ListRepository(connection)
        existing_slugs = {
            definition.slug
            for definition in repository.list_definitions(account_id)
            if definition.slug is not None
        }
        for slug, name in PREDEFINED_LISTS:
            if slug in existing_slugs:
                continue
            repository.create_definition(
                ListDefinition(
                    account_id=account_id,
                    name=name,
                    slug=slug,
                    is_predefined=True,
                    created_at=datetime.now(),
                )
            )
        return repository.list_definitions(account_id)


def list_definitions(account_id: int) -> list[ListDefinition]:
    return ensure_predefined_lists(account_id)


# Every `ValueError` below is raised *outside* a `get_connection` block on
# purpose. These are validation results meant for the user, not database
# failures — raised inside, `get_connection`'s `except` would log each one as
# "Database operation failed, rolled back" with a full traceback, which is
# untrue and would bury real failures in `logs/`. Same reasoning
# `library_service.launch_game` already documents for its expected errors.


def create_list(account_id: int, name: str) -> ListDefinition:
    """Raises `ValueError` (message meant for the user) on a blank or
    duplicate name."""
    with get_connection() as connection:
        existing = ListRepository(connection).list_definitions(account_id)

    cleaned = validate_new_list_name(name, existing)

    with get_connection() as connection:
        return ListRepository(connection).create_definition(
            ListDefinition(
                account_id=account_id,
                name=cleaned,
                slug=None,
                is_predefined=False,
                created_at=datetime.now(),
            )
        )


def rename_list(account_id: int, list_id: int, name: str) -> None:
    """Predefined lists can be renamed but not deleted — the name is just a
    label, while the `slug` that code depends on is untouched."""
    with get_connection() as connection:
        others = [
            definition
            for definition in ListRepository(connection).list_definitions(account_id)
            if definition.id != list_id
        ]

    cleaned = validate_new_list_name(name, others)

    with get_connection() as connection:
        ListRepository(connection).rename_definition(list_id, cleaned)


def delete_list(list_id: int) -> None:
    """Raises `ValueError` for a predefined list. Explorer's blocked filter
    and the Library view resolve by slug, so deleting one of those would
    quietly disable a feature rather than just removing a list.
    """
    with get_connection() as connection:
        definition = ListRepository(connection).get_definition(list_id)

    if definition is None:
        return
    if definition.is_predefined:
        raise ValueError(f'"{definition.name}" is a built-in list and can\'t be deleted.')

    with get_connection() as connection:
        ListRepository(connection).delete_definition(list_id)


def get_definition(list_id: int) -> Optional[ListDefinition]:
    with get_connection() as connection:
        return ListRepository(connection).get_definition(list_id)


def add_to_list(account_id: int, game_id: int, list_id: int) -> None:
    """Raises `ValueError` for Library, whose membership comes from what's
    installed on disk and has nowhere to record a manual addition."""
    with get_connection() as connection:
        definition = ListRepository(connection).get_definition(list_id)

    if definition is None:
        return
    if not definition.accepts_manual_membership:
        raise ValueError(
            f'"{definition.name}" fills itself from your installed ROMs — '
            "add the game there instead."
        )

    with get_connection() as connection:
        ListRepository(connection).add_to_list(
            ListEntry(
                account_id=account_id,
                game_id=game_id,
                list_id=list_id,
                list_type=definition.slug,
                added_at=datetime.now(),
            )
        )


def remove_from_list(account_id: int, game_id: int, list_id: int) -> None:
    with get_connection() as connection:
        ListRepository(connection).remove_from_list(account_id, game_id, list_id)


def get_list_ids_for_game(account_id: int, game_id: int) -> set[int]:
    with get_connection() as connection:
        return ListRepository(connection).get_list_ids_for_game(account_id, game_id)


def get_games_in_list(account_id: int, list_id: int) -> list[Game]:
    """Full `Game` rows for a list screen (UI.md 3.6 — reuses the Game Card)."""
    with get_connection() as connection:
        repository = ListRepository(connection)
        definition = repository.get_definition(list_id)
        if definition is None:
            return []
        return _get_games_in_list(
            account_id,
            definition,
            list_repository=repository,
            game_repository=GameRepository(connection),
        )
