"""QuickLink DTO — one user-chosen reference URL per console (e.g. a
homebrew catalog or wiki), opened externally, never fetched by the app.
"""

from dataclasses import dataclass


@dataclass
class QuickLink:
    console_id: int
    url: str
