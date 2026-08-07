"""Compact list row: cover, title, console, and a "−" to remove it.

Used by the Blocked list and by lists the user created. Both are places you
go to *manage* membership, not to browse or launch — Blocked exists to
unblock, and a custom list exists to curate. A Play button and a "..."
buttons are noise there, so this deliberately carries neither.

Shaped after the Explorer search results (cover + title + console) so the
same game reads the same way in both places.
"""

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.models.game import Game

# One line per game, but a substantial one. The first version stacked title
# and console in a QVBoxLayout and read as oversized panels; the second
# over-corrected to a 32px cover in a 40px strip, which left the row looking
# stretched and empty. These sizes fill the row properly without going back
# to a card.
COVER_SIZE = QSize(64, 64)
ROW_HEIGHT = 76
REMOVE_BUTTON_TEXT = "−"
REMOVE_BUTTON_SIZE = QSize(40, 40)
# Slightly up from the default so the title carries the row's height.
TITLE_POINT_SIZE_DELTA = 1
_LAYOUT_MARGIN = 6
_LAYOUT_SPACING = 12


class ListEntryRow(QFrame):
    remove_requested = Signal(int)  # game_id

    def __init__(
        self,
        game: Game,
        image_loader: ImageLoader,
        console_name: Optional[str] = None,
        remove_tooltip: str = "Remove from this list",
    ) -> None:
        super().__init__()
        self.game = game
        self.setFrameShape(QFrame.Shape.Box)
        # Fixed height, not just a tight layout: without it a long title
        # wraps and the row grows, so a list of them ends up ragged.
        self.setFixedHeight(ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._cover_label = QLabel()
        self._cover_label.setFixedSize(COVER_SIZE)
        image_loader.image_ready.connect(self._on_image_ready)
        image_loader.request(game)

        # Console inline, in parentheses right after the title — one label,
        # not two. It used to be a separate right-aligned label, which left a
        # gap of dead space between the title and it on every short name.
        console_text = console_name or f"Console #{game.console_id}"
        title_label = QLabel(f"{game.title} ({console_text})")
        title_label.setToolTip(title_label.text())
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + TITLE_POINT_SIZE_DELTA)
        title_label.setFont(title_font)
        title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        remove_button = QPushButton(REMOVE_BUTTON_TEXT)
        remove_button.setFixedSize(REMOVE_BUTTON_SIZE)
        remove_button.setToolTip(remove_tooltip)
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self.game.id))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            _LAYOUT_MARGIN, _LAYOUT_MARGIN, _LAYOUT_MARGIN, _LAYOUT_MARGIN
        )
        layout.setSpacing(_LAYOUT_SPACING)
        layout.addWidget(self._cover_label)
        # The title takes all the slack, so the "−" stays hard against the
        # right edge and the space in between belongs to the name.
        layout.addWidget(title_label, stretch=1)
        layout.addWidget(remove_button)

    def _on_image_ready(self, game_id: int, pixmap: Optional[QPixmap]) -> None:
        if game_id != self.game.id or pixmap is None:
            return
        self._cover_label.setPixmap(
            pixmap.scaled(
                COVER_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
