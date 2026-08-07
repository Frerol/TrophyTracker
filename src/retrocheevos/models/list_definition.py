"""One user-visible list — maps to `user_list_definitions` (schema v15).

Predefined lists carry a `slug` (a `ListType` value) because code branches on
them; lists the user creates have `slug = None` and are identified only by
their name.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from retrocheevos.utils.enums import ListType


@dataclass
class ListDefinition:
    account_id: int
    name: str
    slug: Optional[ListType] = None
    is_predefined: bool = False
    created_at: Optional[datetime] = None
    id: Optional[int] = None

    @property
    def is_library(self) -> bool:
        """Resolved from installed ROMs, never from `user_lists` rows — see
        `core/lists.py::get_games_in_list`."""
        return self.slug == ListType.LIBRARY

    @property
    def is_blocked(self) -> bool:
        return self.slug == ListType.BLOCKED

    @property
    def accepts_manual_membership(self) -> bool:
        """False for Library: its contents come from what's installed on
        disk, so "add this game to Library" has nowhere to write. Every other
        list, predefined or not, takes games directly.
        """
        return not self.is_library
