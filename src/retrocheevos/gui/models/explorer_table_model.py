"""Explorer table model (UI.md 3.2) — `QAbstractTableModel` backing the
Game list table, matching the RetroAchievements site layout. `QTableView`
only ever paints visible rows via delegates, so this is what gives the
table its virtualization for free — no per-row widget pool needed (unlike
a card widget, this model has no interactive children to construct).

Owns the in-memory cover-art cache and drives `gui/image_loader.py`: a
cache-miss on `Qt.ItemDataRole.DecorationRole` kicks off a background load,
and `dataChanged` is emitted for that row once it arrives.
"""

from collections import OrderedDict
import time
from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QPixmap

from retrocheevos.core.explorer import GameWithCompletion
from retrocheevos.gui.delegates.explorer_delegates import (
    GAME_ID_ROLE,
    ICON_SIZE,
    INSTALLED_ROLE,
)
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.models.game import Game

COLUMN_TITLE = 0
COLUMN_CONSOLE = 1
COLUMN_TYPE = 2
COLUMN_MEDIAN_TIME = 3
COLUMN_INSTALLED = 4
COLUMN_PROGRESS = 5
COLUMN_ACTIONS = 6

COLUMN_HEADERS = ["Title", "Console", "Type", "Median Time", "Installed", "Progress", ""]

SECONDS_PER_HOUR = 3600
# Sort sentinel for "unknown" Median Time/Progress values -- sorts as the
# smallest value regardless of direction reversal, keeping unknowns out of
# the way rather than interleaved with real numbers.
_UNKNOWN_SORT_VALUE = -1


def _format_median_time(seconds: Optional[int]) -> str:
    """Human duration, matching `widgets/game_card.py`'s wording.

    The sample size (`n=…`) this used to append is a statistical detail
    about how RA derived the figure, not something to weigh up when picking
    a game — and "1.5h (n=33)" read like raw data rather than an answer.
    """
    if seconds is None:
        return "Unknown"
    hours, remainder = divmod(int(seconds), SECONDS_PER_HOUR)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


IMAGE_CACHE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_FAILURES = 1024
IMAGE_RETRY_SECONDS = 30.0


class ExplorerTableModel(QAbstractTableModel):
    def __init__(self, image_loader: ImageLoader) -> None:
        super().__init__()
        self._results: list[GameWithCompletion] = []
        self._sort_column = COLUMN_TITLE
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._console_names: dict[int, str] = {}
        self._installed_game_ids: set[int] = set()
        self._image_cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._image_pending: set[int] = set()
        self._image_failures: OrderedDict[int, float] = OrderedDict()
        self._image_loader = image_loader
        self._image_loader.image_ready.connect(self._on_image_ready)
        # 32-bit scaled thumbnails: at most 4 MiB of pixel data per model.
        self._max_image_cache = max(1, IMAGE_CACHE_BYTES // (ICON_SIZE ** 2 * 4))
        self._failure_retry_seconds = IMAGE_RETRY_SECONDS
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(int(IMAGE_RETRY_SECONDS * 1000))
        self._retry_timer.timeout.connect(self._expire_failures)

    def set_data(
        self,
        results: list[GameWithCompletion],
        console_names: dict[int, str],
        installed_game_ids: set[int],
    ) -> None:
        self.beginResetModel()
        self._results = list(results)
        self._console_names = console_names
        self._installed_game_ids = installed_game_ids
        self._sort_results()
        self.endResetModel()

    def _sort_key(self, result: GameWithCompletion) -> str | int | float:
        game = result.game
        if self._sort_column == COLUMN_TITLE:
            return game.title
        if self._sort_column == COLUMN_CONSOLE:
            return self._console_names.get(game.console_id, f"Console #{game.console_id}")
        if self._sort_column == COLUMN_TYPE:
            return game.game_type.value if game.game_type else "—"
        if self._sort_column == COLUMN_MEDIAN_TIME:
            value = game.median_time_to_beat_hardcore_seconds
            return value if value is not None else _UNKNOWN_SORT_VALUE
        if self._sort_column == COLUMN_INSTALLED:
            return game.id in self._installed_game_ids
        if self._sort_column == COLUMN_PROGRESS:
            return result.percent_complete if result.percent_complete is not None else _UNKNOWN_SORT_VALUE
        return 0

    def _sort_results(self) -> None:
        # Key extraction runs once per row, instead of Qt crossing the Python
        # data()/index boundary twice per comparison during every reset.
        self._results.sort(key=self._sort_key, reverse=self._sort_order == Qt.SortOrder.DescendingOrder)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= column < len(COLUMN_HEADERS):
            return
        self._sort_column, self._sort_order = column, order
        self.layoutAboutToBeChanged.emit()
        persistent = self.persistentIndexList()
        identities = [(self._results[index.row()].game.id, index.column()) for index in persistent]
        self._sort_results()
        rows = {result.game.id: row for row, result in enumerate(self._results)}
        self.changePersistentIndexList(persistent, [self.index(rows[key], col) for key, col in identities])
        self.layoutChanged.emit()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._results)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMN_HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMN_HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        result = self._results[index.row()]
        game = result.game
        column = index.column()

        if role == GAME_ID_ROLE:
            return game.id

        if role == INSTALLED_ROLE:
            return game.id in self._installed_game_ids

        if column == COLUMN_TITLE:
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return game.title
            if role == Qt.ItemDataRole.DecorationRole:
                return self._pixmap_for(game)

        elif column == COLUMN_CONSOLE:
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return self._console_names.get(game.console_id, f"Console #{game.console_id}")

        elif column == COLUMN_TYPE:
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return game.game_type.value if game.game_type else "—"

        elif column == COLUMN_MEDIAN_TIME:
            seconds = game.median_time_to_beat_hardcore_seconds
            if role == Qt.ItemDataRole.DisplayRole:
                return _format_median_time(seconds)
            if role == Qt.ItemDataRole.EditRole:
                return seconds if seconds is not None else _UNKNOWN_SORT_VALUE

        elif column == COLUMN_INSTALLED:
            installed = game.id in self._installed_game_ids
            if role == Qt.ItemDataRole.DisplayRole:
                return "Yes" if installed else "No"
            if role == Qt.ItemDataRole.EditRole:
                return installed

        elif column == COLUMN_PROGRESS:
            percent = result.percent_complete
            if role == Qt.ItemDataRole.DisplayRole:
                return f"{percent:.0f}%" if percent is not None else "—"
            if role == Qt.ItemDataRole.EditRole:
                return percent if percent is not None else float(_UNKNOWN_SORT_VALUE)
            if role == Qt.ItemDataRole.UserRole:
                return percent  # raw value (or None) for the progress-bar delegate

        return None

    def _pixmap_for(self, game: Game) -> Optional[QPixmap]:
        now = time.monotonic()
        if game.id in self._image_failures:
            if now < self._image_failures[game.id]:
                return None
            del self._image_failures[game.id]

        if game.id in self._image_cache:
            self._image_cache.move_to_end(game.id)
            return self._image_cache[game.id]
        if game.id not in self._image_pending:
            self._image_pending.add(game.id)
            self._image_loader.request(game)
        return None

    def _expire_failures(self) -> None:
        now = time.monotonic()
        expired = {key for key, deadline in self._image_failures.items() if deadline <= now}
        for key in expired:
            del self._image_failures[key]
        if not self._image_failures:
            self._retry_timer.stop()
        # Repaint expired visible covers even if the user hasn't interacted.
        for row, result in enumerate(self._results):
            if result.game.id in expired:
                index = self.index(row, COLUMN_TITLE)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    def _on_image_ready(self, game_id: int, pixmap: Optional[QPixmap]) -> None:
        # Scaled once here, not on every repaint: `TitleDelegate.paint()`
        # used to call `pixmap.scaled(...)` itself, allocating a brand-new
        # QPixmap on every single paint of every visible row — a fullscreen
        # resize forces dozens of rows to repaint at once, turning into a
        # burst of scale operations concentrated in one paint cycle.
        self._image_pending.discard(game_id)
        if pixmap is not None:
            pixmap = pixmap.scaled(
                ICON_SIZE,
                ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_failures.pop(game_id, None)
            self._image_cache[game_id] = pixmap
            # Keep the cache bounded after a successful load too.
            while len(self._image_cache) > self._max_image_cache:
                self._image_cache.popitem(last=False)
        else:
            # Failed load: do not cache None forever; retry after a short delay.
            self._image_cache.pop(game_id, None)
            self._image_failures[game_id] = time.monotonic() + self._failure_retry_seconds
            self._image_failures.move_to_end(game_id)
            while len(self._image_failures) > MAX_IMAGE_FAILURES:
                self._image_failures.popitem(last=False)
            if not self._retry_timer.isActive():
                self._retry_timer.start()
        for row, result in enumerate(self._results):
            if result.game.id == game_id:
                changed_index = self.index(row, COLUMN_TITLE)
                self.dataChanged.emit(changed_index, changed_index, [Qt.ItemDataRole.DecorationRole])
                return
