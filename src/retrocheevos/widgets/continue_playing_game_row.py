"""Compact Continue Playing card for games with a real match — presentation-
only sibling of `widgets/installed_game_frame.py`, the Library's card. Same
shape (cover, caption, click-to-play); this one adds the progress bar, which
is the only thing that distinguishes the two grids.

Cover art reuses the exact async mechanism the Explorer table already uses
(`gui/image_loader.py::ImageLoader` -> `services/image_service.py`
`ensure_game_image_cached`, disk-cached by `game.id`) rather than inventing a
second image pipeline — this row requests its own image and filters the
shared loader's `image_ready` broadcast by `game.id`, the same shape as
`gui/models/explorer_table_model.py`'s per-row image handling.
"""

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
)

from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.library.console_names import abbreviate_console
from retrocheevos.models.game import Game
from retrocheevos.widgets.cover_art import fill_square
from retrocheevos.widgets.text_layout import wrap_lines

# Small enough that six cards fit across Home's grid without the text
# column being squeezed to nothing (`CONTINUE_PLAYING_GRID_COLUMNS`).
COVER_SIZE = QSize(40, 40)
# Slim enough not to dominate a compact card, tall enough to read.
PROGRESS_BAR_HEIGHT = 14
# Two elided lines, same rule as `installed_game_frame.py`.
MAX_TITLE_LINES = 2
CAPTION_LINES = MAX_TITLE_LINES + 1
CAPTION_SIDE_PAD = 6
CAPTION_MIN_COVER = 90
MARGIN_RATIO = 0.04
MIN_MARGIN = 2


class ContinuePlayingGameRow(QFrame):
    play_requested = Signal(int)  # game_id

    def __init__(
        self,
        game: Game,
        image_loader: ImageLoader,
        console_name: Optional[str] = None,
        percent_complete: Optional[float] = None,
        cover_size: Optional[int] = None,
    ) -> None:
        """`cover_size` overrides `COVER_SIZE` — Home's slider passes it."""
        super().__init__()
        self.game = game
        edge = cover_size or COVER_SIZE.width()
        self._cover_size = QSize(edge, edge)
        self.setFrameShape(QFrame.Shape.Box)
        # Fixed vertically. The Continue Playing group stretches to fill the
        # column, and a QFrame's default Preferred policy lets it grow with
        # it — one card was inflating to the full panel height around a 40px
        # cover. Aligning the grid to the top isn't enough on its own; the
        # widget has to refuse the extra height too.
        # Fixed on *both* axes, like `InstalledGameFrame`. Horizontally
        # `Preferred` let a lone card absorb its whole grid column — at 40px
        # covers that meant a tiny picture floating in a very wide box, which
        # looks exactly like the slider not working.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._cover_label = QLabel()
        self._cover_label.setFixedSize(self._cover_size)
        image_loader.image_ready.connect(self._on_image_ready)
        image_loader.request(game)

        console_text = console_name or f"Console #{game.console_id}"
        console_short = abbreviate_console(console_text)
        self.setToolTip(f"{game.title} ({console_text}) — click to play")

        # A real bar, not just the number: at a glance across a row of cards
        # the filled width is what's readable. "No progress" for the no-data
        # case, which is the common one — most
        # installed games have no `game_completion` row at all (they're
        # listed here because they're installed, not because they've been
        # started), so that's the common state, not an edge.
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setFixedHeight(PROGRESS_BAR_HEIGHT)
        progress_bar.setFixedWidth(self._cover_size.width())
        progress_bar.setValue(round(percent_complete) if percent_complete is not None else 0)
        if edge < CAPTION_MIN_COVER:
            # No room for a legible label inside a bar this narrow — the fill
            # still reads at a glance, and "No progr…" clipped mid-word
            # doesn't.
            progress_bar.setFormat("")
        else:
            progress_bar.setFormat(
                f"{percent_complete:.0f}%" if percent_complete is not None else "No progress"
            )

        # No "Continue" button: the cover is the button, matching the Library
        # grid (`widgets/installed_game_frame.py`). Clicking the art is the
        # whole interaction, so a label repeating it underneath was a second
        # control for the same action taking up a third of a compact card.
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Click to play {game.title}")

        # Vertical, matching the Library grid: cover on top, title under it,
        # progress bar under that. This was a horizontal strip (cover left,
        # text right), which no longer made sense once the cover became the
        # button and the covers became resizable — a wide short card wastes
        # the height the art wants.
        margin = max(MIN_MARGIN, round(edge * MARGIN_RATIO))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(margin)
        layout.addWidget(self._cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        # Caption dropped on small covers (same rule as `InstalledGameFrame`)
        # — the tooltip carries the name. The progress bar always stays: it's
        # the only thing distinguishing this card from a Library one, and at
        # a few pixels tall it costs nothing.
        if edge >= CAPTION_MIN_COVER:
            title_label = QLabel()
            title_label.setAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            )
            # Elided, not wrapped, and measured only after `ensurePolished()`
            # so the font is the stylesheet's rather than the default — see
            # `installed_game_frame.py` for why both parts matter.
            title_label.ensurePolished()
            metrics = QFontMetrics(title_label.font())
            available = edge - CAPTION_SIDE_PAD
            lines = wrap_lines(game.title, metrics, available, MAX_TITLE_LINES)
            lines += wrap_lines(console_short, metrics, available, 1)
            title_label.setText("\n".join(lines))
            # Worst-case height for every card, so the row doesn't come out
            # ragged — see `installed_game_frame.py`.
            title_label.setFixedSize(edge, metrics.lineSpacing() * CAPTION_LINES)
            layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(progress_bar, alignment=Qt.AlignmentFlag.AlignHCenter)

    def mousePressEvent(self, event) -> None:
        """Left-click anywhere on the card launches. Right-click falls through
        to the default handler, so a context menu stays possible later."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.play_requested.emit(self.game.id)
            return
        super().mousePressEvent(event)

    def _on_image_ready(self, game_id: int, pixmap: Optional[QPixmap]) -> None:
        if game_id != self.game.id or pixmap is None:
            return
        self._cover_label.setPixmap(fill_square(pixmap, self._cover_size))
