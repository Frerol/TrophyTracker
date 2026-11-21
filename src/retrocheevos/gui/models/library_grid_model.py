"""Model behind the Library cover grid (R22).

One row per `LibraryEntry` after filtering. Covers are requested only when a
row is painted (`DecorationRole`), scaled once, and kept in an LRU bounded by
the same pixel budget as the Explorer table (R07), so a library of thousands
of ROMs costs the visible cards, not the whole collection.
"""

import time
from collections import OrderedDict
from typing import Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QPixmap

from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.models.explorer_table_model import IMAGE_CACHE_BYTES, IMAGE_RETRY_SECONDS
from retrocheevos.library.console_names import abbreviate_console
from retrocheevos.library.local_covers import cached_local_cover_path
from retrocheevos.models.game import Game
from retrocheevos.models.library import LibraryEntry

COVER_EDGE = 128

EntryRole = Qt.ItemDataRole.UserRole + 1
CaptionRole = Qt.ItemDataRole.UserRole + 2
ProgressRole = Qt.ItemDataRole.UserRole + 3  # Optional[float] in 0..1
PlayReasonRole = Qt.ItemDataRole.UserRole + 4  # Optional[str]
ConsoleRole = Qt.ItemDataRole.UserRole + 5
FallbackRole = Qt.ItemDataRole.UserRole + 6

PROGRESS_UNAVAILABLE = "Progress unavailable"
NO_MATCH = "No catalog match"
NO_EMULATOR = "No emulator"


def progress_caption(entry: LibraryEntry) -> tuple[str, Optional[float]]:
    """("34/42 achievements", 0.81) — unknown progress is never zero (D8)."""
    if entry.kind == "rom":
        return NO_MATCH, None
    if entry.achievements_unlocked is not None and entry.achievements_total:
        unlocked = max(0, min(entry.achievements_unlocked, entry.achievements_total))
        return f"{unlocked}/{entry.achievements_total} achievements", unlocked / entry.achievements_total
    if entry.percent_complete is not None:
        percent = max(0.0, min(entry.percent_complete, 100.0))
        return f"{percent:.0f}% complete", percent / 100
    return PROGRESS_UNAVAILABLE, None


class LibraryGridModel(QAbstractListModel):
    def __init__(self, image_loader: ImageLoader, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[LibraryEntry] = []
        self._rows: dict[tuple[str, int], int] = {}
        self._console_names: dict[int, str] = {}
        self._cover_games: dict[int, Game] = {}
        self._loader = image_loader
        self._cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
        self._pending: set[tuple[str, int]] = set()
        self._failures: dict[tuple[str, int], float] = {}
        self._max_cache = max(1, IMAGE_CACHE_BYTES // (COVER_EDGE ** 2 * 4))
        self._retry_seconds = IMAGE_RETRY_SECONDS
        image_loader.image_ready.connect(self._on_game_image)
        image_loader.rom_image_ready.connect(self._on_rom_image)
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(int(IMAGE_RETRY_SECONDS * 1000))
        self._retry_timer.timeout.connect(self._expire_failures)

    # Data ------------------------------------------------------------------

    def set_entries(
        self,
        entries: list[LibraryEntry],
        console_names: dict[int, str],
        cover_games: Optional[dict[int, Game]] = None,
    ) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self._rows = {entry.key: row for row, entry in enumerate(self._entries)}
        self._console_names = console_names
        self._cover_games = cover_games or {}
        self.endResetModel()

    def entries(self) -> list[LibraryEntry]:
        return list(self._entries)

    def entry(self, index: QModelIndex) -> Optional[LibraryEntry]:
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        return self._entries[index.row()]

    def console_name(self, console_id: int) -> str:
        return self._console_names.get(console_id, f"Console #{console_id}")

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 — Qt override
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        entry = self.entry(index)
        if entry is None:
            return None
        console = self.console_name(entry.console_id)
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.title
        if role == EntryRole:
            return entry
        if role == ConsoleRole:
            return console
        if role == FallbackRole:
            return abbreviate_console(console)
        if role == CaptionRole:
            return progress_caption(entry)[0]
        if role == ProgressRole:
            return progress_caption(entry)[1]
        if role == PlayReasonRole:
            return None if entry.has_emulator else NO_EMULATOR
        if role == Qt.ItemDataRole.ToolTipRole:
            if entry.kind == "rom":
                return (f"{entry.title}\n{console} · {NO_MATCH}: this file's hash is not in "
                        "the synced catalog. Right-click → Match to game… to choose it.")
            manual = " · game chosen by hand" if entry.manual_roms else ""
            return f"{entry.title}\n{console} · {progress_caption(entry)[0]}{manual}"
        if role == Qt.ItemDataRole.AccessibleTextRole:
            text = f"{entry.title}, {console}, {progress_caption(entry)[0]}"
            return text if entry.has_emulator else f"{text}, no emulator configured"
        if role == Qt.ItemDataRole.DecorationRole:
            return self._cover_for(entry)
        return None

    # Covers ----------------------------------------------------------------

    def requested_keys(self) -> set[tuple[str, int]]:
        return set(self._pending) | set(self._cache) | set(self._failures)

    def cached_bytes(self) -> int:
        return sum(p.width() * p.height() * 4 for p in self._cache.values())

    def _cover_for(self, entry: LibraryEntry) -> Optional[QPixmap]:
        key = entry.key
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if entry.kind == "rom":
            # A cover the user picked by hand always wins, and needs no load.
            local = QPixmap(str(cached_local_cover_path(entry.rom.id)))
            if not local.isNull():
                self._store(key, local)
                return self._cache[key]
        if key in self._pending:
            return None
        deadline = self._failures.get(key)
        if deadline is not None:
            if time.monotonic() < deadline:
                return None
            del self._failures[key]
        self._pending.add(key)
        if entry.kind == "game":
            self._loader.request(entry.game)
        else:
            self._loader.request_rom(entry.rom, self._cover_games.get(entry.rom.id))
        return None

    def forget_cover(self, key: tuple[str, int]) -> None:
        """Drop a cached cover (a new user cover, or a changed file)."""
        self._cache.pop(key, None)
        self._failures.pop(key, None)
        self._pending.discard(key)
        self._notify(key)

    def _store(self, key: tuple[str, int], pixmap: QPixmap) -> None:
        self._cache[key] = pixmap.scaled(
            COVER_EDGE, COVER_EDGE, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        while len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)

    def _on_game_image(self, game_id: int, pixmap: Optional[QPixmap]) -> None:
        self._on_image(("game", game_id), pixmap)

    def _on_rom_image(self, rom_id: int, pixmap: Optional[QPixmap]) -> None:
        self._on_image(("rom", rom_id), pixmap)

    def _on_image(self, key: tuple[str, int], pixmap: Optional[QPixmap]) -> None:
        if key not in self._pending:
            return
        self._pending.discard(key)
        if pixmap is None or pixmap.isNull():
            self._failures[key] = time.monotonic() + self._retry_seconds
            if not self._retry_timer.isActive():
                self._retry_timer.start()
            return
        self._store(key, pixmap)
        self._notify(key)

    def _notify(self, key: tuple[str, int]) -> None:
        row = self._rows.get(key)
        if row is not None:
            index = self.index(row)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    def _expire_failures(self) -> None:
        now = time.monotonic()
        expired = [key for key, deadline in self._failures.items() if deadline <= now]
        for key in expired:
            del self._failures[key]
            self._notify(key)
        if not self._failures:
            self._retry_timer.stop()
