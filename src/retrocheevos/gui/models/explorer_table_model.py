"""Explorer table model (UI.md 3.2) — `QAbstractTableModel` backing the
Game list table, matching the RetroAchievements site layout. `QTableView`
only ever paints visible rows via delegates, so this is what gives the
table its virtualization for free — no per-row widget pool needed (unlike
a card widget, this model has no interactive children to construct).

Owns the in-memory cover-art cache and drives `gui/image_loader.py`: a
cache-miss on `Qt.ItemDataRole.DecorationRole` kicks off a background load,
and `dataChanged` is emitted for that row once it arrives.
"""

from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
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


class ExplorerTableModel(QAbstractTableModel):
    def __init__(self, image_loader: ImageLoader) -> None:
        super().__init__()
        self._results: list[GameWithCompletion] = []
        self._console_names: dict[int, str] = {}
        self._installed_game_ids: set[int] = set()
        self._image_cache: dict[int, Optional[QPixmap]] = {}
        self._image_loader = image_loader
        self._image_loader.image_ready.connect(self._on_image_ready)

    def set_data(
        self,
        results: list[GameWithCompletion],
        console_names: dict[int, str],
        installed_game_ids: set[int],
    ) -> None:
        self.beginResetModel()
        self._results = results
        self._console_names = console_names
        self._installed_game_ids = installed_game_ids
        self.endResetModel()

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
        if game.id not in self._image_cache:
            self._image_cache[game.id] = None  # marks "requested", avoids re-requesting on repaint
            self._image_loader.request(game)
        return self._image_cache[game.id]

    def _on_image_ready(self, game_id: int, pixmap: Optional[QPixmap]) -> None:
        # Scaled once here, not on every repaint: `TitleDelegate.paint()`
        # used to call `pixmap.scaled(...)` itself, allocating a brand-new
        # QPixmap on every single paint of every visible row — a fullscreen
        # resize forces dozens of rows to repaint at once, turning into a
        # burst of scale operations concentrated in one paint cycle.
        if pixmap is not None:
            pixmap = pixmap.scaled(
                ICON_SIZE,
                ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._image_cache[game_id] = pixmap
        for row, result in enumerate(self._results):
            if result.game.id == game_id:
                changed_index = self.index(row, COLUMN_TITLE)
                self.dataChanged.emit(changed_index, changed_index, [Qt.ItemDataRole.DecorationRole])
                return
