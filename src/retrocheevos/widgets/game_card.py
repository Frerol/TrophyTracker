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

        title_label = QLabel(game.title)
        title_label.setWordWrap(True)
        # Presentation-only (Architecture.md): this widget doesn't look up
        # the console name itself — the owning page resolves it and passes
        # it in. Falls back to the raw id if the page doesn't have it yet.
        console_label = QLabel(console_name or f"Console #{game.console_id}")
        median_label = QLabel(self._format_median_time())

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(round(percent_complete) if percent_complete is not None else 0)
        progress_bar.setFormat(
            f"{percent_complete:.0f}%" if percent_complete is not None else "No progress"
        )

        play_button = QPushButton("Play")
        play_button.clicked.connect(lambda: self.play_requested.emit(self.game.id))

        menu_button = QPushButton("...")
        menu = QMenu(menu_button)
        for list_type, label in LIST_ACTION_LABELS.items():
            action = menu.addAction(label)
            action.triggered.connect(self._make_list_action_handler(list_type))
        menu.addSeparator()
        open_action = menu.addAction("Open on RetroAchievements")
        open_action.setEnabled(bool(game.retroachievements_url))
        open_action.triggered.connect(self._open_on_retroachievements)
        menu_button.setMenu(menu)

        action_row = QHBoxLayout()
        action_row.addWidget(play_button)
        action_row.addWidget(menu_button)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(console_label)
        layout.addWidget(median_label)
        layout.addWidget(progress_bar)
        layout.addLayout(action_row)

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
