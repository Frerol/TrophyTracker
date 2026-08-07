"""List membership rules (Database.md 4.1) — `services/lists_service.py`'s
Core counterpart, matching `core/explorer.py`/`core/dashboard.py`.
"""

from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.database.repositories.list_repository import ListRepository
from retrocheevos.models.game import Game
from retrocheevos.models.list_definition import ListDefinition
from retrocheevos.utils.enums import ListType

# Blocked is the only list the app creates for you.
#
# Want to Play / Playing / Completed / Abandoned were predefined too, and
# were dropped (migration v16, per user decision — they were empty). They
# had never been anything but names the app happened to ship: with
# user-created lists in place, someone who wants a "Playing" list can make
# one, and someone who doesn't isn't stuck looking at it.
#
# Blocked stays because code depends on it existing — Explorer hides its
# games on every search. Library is no longer a list at all: it became its
# own page (`gui/pages/library_page.py`), since it never behaved like one —
# no stored rows, no manual membership, and a completely different layout.
PREDEFINED_LISTS: list[tuple[ListType, str]] = [
    (ListType.BLOCKED, "Blocked"),
]


def get_games_in_list(
    account_id: int,
    definition: ListDefinition,
    *,
    list_repository: ListRepository,
    game_repository: GameRepository,
) -> list[Game]:
    """Full `Game` rows for one list.

    A blocked game is excluded from every *other* list's view — being blocked
    hides it everywhere except the Blocked list itself, which is where it gets
    unblocked (Database.md 4.1).
    """
    game_ids = list_repository.get_game_ids_in_list(account_id, definition.id)

    if not definition.is_blocked:
        blocked_ids = list_repository.get_game_ids_by_slug(account_id, ListType.BLOCKED)
        game_ids = game_ids - blocked_ids

    games = (game_repository.get_by_id(game_id) for game_id in game_ids)
    # `get_by_id` is intentionally left unfiltered (ROM-hash matching in
    # `services/library_service.py` needs it to still resolve a game even if
    # it has no achievement set) — guard against it resurfacing one here.
    return [game for game in games if game is not None and game.has_achievements]


def get_installed_games(
    account_id: int,
    *,
    list_repository: ListRepository,
    game_repository: GameRepository,
    library_repository: LibraryRepository,
) -> list[Game]:
    """What the Library page shows: every game with a matched local ROM.

    Computed, never stored — the answer is whatever `installed_roms` says
    right now. Storing it would mean every scan had to add and remove rows to
    stay truthful, and deleting a ROM off disk would leave a game listed as
    installed.

    Lives in `core/` next to the list rules rather than in the service
    because of the blocked filter: "a blocked game is hidden everywhere" is
    the same rule the lists obey, and it would drift if written twice.
    Sorted by title so the grid has a stable order — `get_installed_game_ids`
    returns a set.
    """
    game_ids = library_repository.get_installed_game_ids()
    game_ids -= list_repository.get_game_ids_by_slug(account_id, ListType.BLOCKED)
    games = (game_repository.get_by_id(game_id) for game_id in game_ids)
    return sorted(
        (game for game in games if game is not None and game.has_achievements),
        key=lambda game: game.title.casefold(),
    )


def validate_new_list_name(name: str, existing: list[ListDefinition]) -> str:
    """Returns the cleaned name, or raises `ValueError` with a message meant
    for the user.

    Case-insensitive collision check, because the underlying unique index is
    `COLLATE NOCASE`-ordered but not case-insensitive itself — without this a
    user could create both "Backlog" and "backlog" and have no way to tell
    them apart in the selector.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("A list needs a name.")
    if any(definition.name.casefold() == cleaned.casefold() for definition in existing):
        raise ValueError(f'You already have a list called "{cleaned}".')
    return cleaned
