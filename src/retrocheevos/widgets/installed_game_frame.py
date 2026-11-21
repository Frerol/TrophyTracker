"""Large cover-art frame for the Library list (UI.md 3.6, Bloco 13).

The whole image is the button. Every other launch surface in this app uses an
explicit button — Home's `ContinuePlayingRow` has "Play", the ROM Location
page has "Play Selected" — but Library is a wall of box art whose only
purpose is launching, so a row of small buttons underneath would be noise.
Clicking the art launches; that's the entire interaction.

Cover art reuses the shared async pipeline (`gui/image_loader.py::ImageLoader`
-> `services/image_service.py`), filtering the loader's `image_ready`
broadcast by `game.id` — the same shape as `ContinuePlayingRow` and
`gui/models/explorer_table_model.py`.
"""

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QSizePolicy, QVBoxLayout

from retrocheevos.gui import styles
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.library.console_names import abbreviate_console
from retrocheevos.models.game import Game
from retrocheevos.widgets.cover_art import fill_square
from retrocheevos.widgets.text_layout import wrap_lines

# Paired with `library_page.GRID_COLUMNS` (6) — the two are chosen together
# or the page scrolls sideways. 104 across 8 columns read as too small; this
# is the compromise back towards legible box art.
COVER_SIZE = QSize(150, 150)
PLACEHOLDER_TEXT = "No cover"
REMOVE_ACTION_TEXT = "Remove from Library"

# Everything below scales with the cover, so the *card* shrinks with the
# slider and not just the picture inside it. These were fixed values, which
# meant a 40px cover still sat in a card padded and captioned for a 150px
# one — the text was clipped by its own fixed box and the card had a floor it
# could never go under, so shrinking the covers just spread empty background.
# Two lines, and the text is **elided to fit** rather than wrapped.
#
# Wrapping into a fixed-height box can always clip: how many lines a title
# needs depends on the title and the width, so any height picked in advance
# is wrong for some combination — first a ratio of the cover, then three
# font-derived lines, both still cut names at some sizes. Eliding is
# deterministic: `elidedText` guarantees one line fits the width, so two
# lines always fit two lines' height, at every cover size, for every title.
# Title may take two lines before anything is elided; the console line
# always gets its own. Every caption reserves all three regardless of what
# it uses, so all frames are the same size.
MAX_TITLE_LINES = 2
CAPTION_LINES = MAX_TITLE_LINES + 1
# Elide against slightly less than the full width: QLabel's own text layout
# rounds, and eliding to the exact box width leaves the last glyph touching
# (occasionally crossing) the edge.
CAPTION_SIDE_PAD = 6
# Under this the caption is dropped entirely: two lines of legible text can't
# fit in the width of a thumbnail, and a clipped half-word is worse than the
# tooltip that replaces it.
CAPTION_MIN_COVER = 90
MARGIN_RATIO = 0.04
MIN_MARGIN = 2
FONT_MIN_COVER = 120
SMALL_FONT_DELTA = -1

# Makes the frame read as clickable before the click. `QLabel` has no hover
# state of its own, so this is on the frame.
FRAME_STYLESHEET = f"""
QFrame#InstalledGameFrame {{
    background-color: {styles.BOX_BG};
    border: 1px solid {styles.EMBED_HIGHLIGHT};
    border-radius: {styles.RADIUS}px;
}}
QFrame#InstalledGameFrame:hover {{
    border: 1px solid {styles.LINK};
}}
"""


class InstalledGameFrame(QFrame):
    play_requested = Signal(int)  # game_id
    remove_requested = Signal(int)  # game_id

    def __init__(
        self,
        game: Game,
        image_loader: ImageLoader,
        console_name: Optional[str] = None,
        cover_size: Optional[int] = None,
    ) -> None:
        """`cover_size` overrides `COVER_SIZE` for this instance — the Library
        page's slider passes the user's chosen edge length."""
        super().__init__()
        self.game = game
        edge = cover_size or COVER_SIZE.width()
        self._cover_size = QSize(edge, edge)
        self.setObjectName("InstalledGameFrame")
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(FRAME_STYLESHEET)
        # `CustomContextMenu` + signal, not a `contextMenuEvent` override:
        # the override never fired, because the right-click lands on one of
        # this frame's child QLabels and a bare override doesn't get it. The
        # policy makes Qt route the request to this widget regardless of
        # which child was under the cursor.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Click to play {game.title}")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._cover_label = QLabel(PLACEHOLDER_TEXT)
        self._cover_label.setFixedSize(self._cover_size)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Stops the pixmap from being drawn outside the label's own box if a
        # cover ever comes back larger than expected.
        self._cover_label.setScaledContents(False)
        image_loader.image_ready.connect(self._on_image_ready)
        image_loader.request(game)

        console_text = console_name or f"Console #{game.console_id}"
        # Short form in the caption, full name in the tooltip — the caption
        # has only the cover's width, and "PSP" is what people call it.
        console_short = abbreviate_console(console_text)
        self.setToolTip(f"{game.title} ({console_text}) — click to play")

        margin = max(MIN_MARGIN, round(edge * MARGIN_RATIO))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(margin)
        layout.addWidget(self._cover_label)

        # Below `CAPTION_MIN_COVER` the card is art only — the tooltip above
        # still names the game, and this is what lets a thumbnail actually be
        # thumbnail-sized instead of a small picture in a large caption box.
        if edge >= CAPTION_MIN_COVER:
            title_label = QLabel()
            title_label.setAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            )
            if edge < FONT_MIN_COVER:
                font = title_label.font()
                font.setPointSize(max(6, font.pointSize() + SMALL_FONT_DELTA))
                title_label.setFont(font)
            # `ensurePolished()` before measuring is essential, not tidiness:
            # the app stylesheet sets the font size, and until the widget is
            # polished `font()` still reports the *default* one. Eliding
            # against that measured too generously and the drawn text — in
            # the larger real font — overflowed anyway. This was the reason
            # captions kept clipping after they were switched to eliding.
            title_label.ensurePolished()
            metrics = QFontMetrics(title_label.font())
            available = edge - CAPTION_SIDE_PAD
            # Wrapped, not elided-on-sight: a title that doesn't fit one line
            # gets a second one, and "…" only appears if it doesn't fit two
            # either. The box is then sized from the lines we actually
            # produced, so it can't clip.
            lines = wrap_lines(game.title, metrics, available, MAX_TITLE_LINES)
            lines += wrap_lines(console_short, metrics, available, 1)
            title_label.setText("\n".join(lines))
            # Height is the *worst case* (`CAPTION_LINES`), identical for
            # every card, not `len(lines)`. Sizing to the lines actually
            # produced made a one-line title a shorter frame than a two-line
            # one, so the grid came out ragged. A short title just leaves its
            # last line blank; the text is top-aligned, so it stays put and
            # the console line sits lower on cards that need two.
            title_label.setFixedSize(edge, metrics.lineSpacing() * CAPTION_LINES)
            layout.addWidget(title_label)

    def build_context_menu(self) -> QMenu:
        """The right-click menu, built but not shown.

        Split from showing it so it can be tested: `QMenu.exec` is a blocking
        C++ call that can't be intercepted from Python, so a handler that
        built *and* ran the menu in one step was unverifiable — and was in
        fact broken without that being visible.
        """
        menu = QMenu(self)
        remove_action = menu.addAction(REMOVE_ACTION_TEXT)
        remove_action.triggered.connect(lambda: self.remove_requested.emit(self.game.id))
        return menu

    def _show_context_menu(self, position) -> None:
        self.build_context_menu().exec(self.mapToGlobal(position))

    def mousePressEvent(self, event) -> None:
        """Left-click anywhere on the frame launches; right-click is left
        alone so the context menu policy can handle it."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.play_requested.emit(self.game.id)
            return
        super().mousePressEvent(event)

    def _on_image_ready(self, game_id: int, pixmap: Optional[QPixmap]) -> None:
        if game_id != self.game.id or pixmap is None:
            return
        self._cover_label.setText("")
        self._cover_label.setPixmap(fill_square(pixmap, self._cover_size))
