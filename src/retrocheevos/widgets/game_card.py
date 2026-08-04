"""Game Card widget (UI.md 4.1, 4.2) — presentation-only (Architecture.md §3.1).

Never calls `services/` directly: it emits Qt signals and leaves the owning
page to act on them, keeping this layer swappable/reusable (e.g. for the
future Steam Deck/Linux GUI adaptation, Architecture.md §5).
"""

from typing import Optional

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from retrocheevos.models.game import Game
from retrocheevos.utils.enums import ListType

SECONDS_PER_HOUR = 3600

LIST_ACTION_LABELS = {
    ListType.WANT_TO_PLAY: "Want to Play",
    ListType.PLAYING: "Playing",
    ListType.ABANDONED: "Abandoned",
    ListType.FOLLOWING: "Following",
}


class GameCard(QFrame):
    # `object`, not `ListType`, on purpose: Qt's signal meta-type system can
    # coerce a str-subclass Enum (ListType) down to a plain str when crossing
    # a signal boundary. `object` passes the Python value through untouched.
    list_action_requested = Signal(int, object)  # game_id, ListType
    play_requested = Signal(int)  # game_id

    def __init__(
        self,
        game: Game,
        percent_complete: Optional[float] = None,
        console_name: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.game = game
        self.setFrameShape(QFrame.Shape.Box)

        self._title_label = QLabel(game.title)
        self._title_label.setWordWrap(True)
        # Presentation-only (Architecture.md): this widget doesn't look up
        # the console name itself — the owning page resolves it and passes
        # it in. Falls back to the raw id if the page doesn't have it yet.
        console_label = QLabel(console_name or f"Console #{game.console_id}")
        self._median_label = QLabel(self._format_median_time())

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._set_progress(percent_complete)

        play_button = QPushButton("Play")
        play_button.clicked.connect(lambda: self.play_requested.emit(self.game.id))

        # The "..." menu (QMenu + 5 QAction, each with a connected signal) is
        # built lazily, on first click, not here. Profiling against a 1500+
        # game library showed this menu alone accounts for roughly a third
        # of GameCard's construction cost — building it eagerly for every
        # card, most of which the user never opens, is wasted work that
        # measurably slows down showing a large filtered result set.
        self._menu_button = QPushButton("...")
        self._menu_button.clicked.connect(self._show_menu)

        action_row = QHBoxLayout()
        action_row.addWidget(play_button)
        action_row.addWidget(self._menu_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title_label)
        layout.addWidget(console_label)
        layout.addWidget(self._median_label)
        layout.addWidget(self._progress_bar)
        layout.addLayout(action_row)

    def update_data(self, game: Game, percent_complete: Optional[float] = None) -> None:
        """Refresh this card's text/progress in place — no widgets rebuilt.

        Lets the owning page reuse an existing card for a game that's still
        in a new filtered result set, instead of destroying and recreating
        it (that per-filter-change full rebuild was the actual cause of the
        Explorer slowdown — see gui/pages/explorer_page.py's `_update_grid`).
        Console name isn't handled here: it never changes for a given game.
        """
        self.game = game
        self._title_label.setText(game.title)
        self._median_label.setText(self._format_median_time())
        self._set_progress(percent_complete)

    def _set_progress(self, percent_complete: Optional[float]) -> None:
        self._progress_bar.setValue(round(percent_complete) if percent_complete is not None else 0)
        self._progress_bar.setFormat(
            f"{percent_complete:.0f}%" if percent_complete is not None else "No progress"
        )

    def _show_menu(self) -> None:
        menu = QMenu(self._menu_button)
        for list_type, label in LIST_ACTION_LABELS.items():
            action = menu.addAction(label)
            action.triggered.connect(self._make_list_action_handler(list_type))
        menu.addSeparator()
        open_action = menu.addAction("Open on RetroAchievements")
        open_action.setEnabled(bool(self.game.retroachievements_url))
        open_action.triggered.connect(self._open_on_retroachievements)
        menu.exec(self._menu_button.mapToGlobal(self._menu_button.rect().bottomLeft()))

    def _make_list_action_handler(self, list_type: ListType):
        return lambda: self.list_action_requested.emit(self.game.id, list_type)

    def _format_median_time(self) -> str:
        seconds = self.game.median_time_to_beat_hardcore_seconds
        if seconds is None:
            return "Median time: unknown"
        hours = seconds / SECONDS_PER_HOUR
        sample = self.game.times_used_in_hardcore_beat_median
        sample_text = f" (n={sample})" if sample else ""
        return f"Median time (HC): {hours:.1f}h{sample_text}"

    def _open_on_retroachievements(self) -> None:
        if self.game.retroachievements_url:
            QDesktopServices.openUrl(QUrl(self.game.retroachievements_url))
