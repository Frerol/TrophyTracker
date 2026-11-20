"""Continue Playing fallback card for installed ROMs with no matched game
(`services/dashboard_service.py::get_unmatched_continue_playing_roms`) —
presentation-only sibling of `widgets/installed_game_frame.py`, deliberately
simpler: no `game_id` means no list-membership menu and no "Open on
RetroAchievements", and Play launches by `installed_rom.id`
(`services/library_service.py::launch_installed_rom`) instead of a game id.

Artwork loads in the background from local files, GameTDB disc IDs or a
catalog artwork guess. User-picked covers take precedence. Clicking plays;
the context menu lets the user replace the cover by hand.
"""

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QProgressBar,
    QSizePolicy,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from retrocheevos.library.local_covers import cached_local_cover_path
from retrocheevos.library.console_names import abbreviate_console
from retrocheevos.library.rom_title import derive_title_from_filename
from retrocheevos.widgets.cover_art import console_placeholder, fill_square
from retrocheevos.widgets.text_layout import wrap_lines
from retrocheevos.models.library import InstalledRom

# Same size as `widgets/continue_playing_game_row.py::COVER_SIZE` — both
# share Continue Playing's compact grid, so their cover slots line up.
COVER_SIZE = QSize(40, 40)
IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"


REMOVE_ACTION_TEXT = "Remove from Library"
PICK_COVER_ACTION_TEXT = "Choose cover…"
# Mirrors `widgets/installed_game_frame.py` so the two card kinds share a
# shape at every cover size.
MAX_TITLE_LINES = 2
CAPTION_LINES = MAX_TITLE_LINES + 1
CAPTION_SIDE_PAD = 6
CAPTION_MIN_COVER = 90
MARGIN_RATIO = 0.04
MIN_MARGIN = 2
# Matches `continue_playing_game_row.PROGRESS_BAR_HEIGHT`, so a row of mixed
# cards lines up.
PROGRESS_BAR_HEIGHT = 14


class UnmatchedRomCard(QFrame):
    play_requested = Signal(int)  # installed_rom_id
    remove_requested = Signal(int)  # installed_rom_id

    def __init__(
        self,
        installed_rom: InstalledRom,
        console_name: Optional[str] = None,
        cover_game=None,
        image_loader=None,
        cover_size: Optional[int] = None,
        show_progress: bool = False,
    ) -> None:
        """`cover_game` is a catalog game whose title and console match this
        ROM's filename closely enough to borrow its artwork
        (`library_service.guess_games_for_unmatched_roms`). It is *only* a
        picture — the ROM stays unmatched, because a title that looks right
        is not the same as a hash that is right.

        A cover the user picked by hand always wins over the guess.
        """
        super().__init__()
        self.installed_rom = installed_rom
        # Same right-click removal as the matched cards
        # (`widgets/installed_game_frame.py`) — an unrecognised file is the
        # case you *most* want to get rid of, so it would be odd for it to be
        # the one card you can't. `CustomContextMenu`, not a
        # `contextMenuEvent` override: the click lands on a child widget and
        # an override never sees it.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setFrameShape(QFrame.Shape.Box)

        # Laid out exactly like `ContinuePlayingGameRow`/`InstalledGameFrame`:
        # cover on top, caption underneath, no "Continue" button. It used to
        # be a horizontal strip with a button, which made unmatched ROMs read
        # as a different kind of thing sitting in the same grid — most
        # visibly once they started getting cover art of their own.
        edge = cover_size or COVER_SIZE.width()
        self._cover_size = QSize(edge, edge)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._cover_button = QPushButton()
        self._cover_button.setFixedSize(self._cover_size)
        self._cover_button.setIconSize(self._cover_size)
        # Clicking the art launches, matching the other cards. Picking a
        # cover by hand moved to the right-click menu — it's the rarer action
        # and it was occupying the gesture everything else uses to play.
        self._cover_button.clicked.connect(
            lambda: self.play_requested.emit(self.installed_rom.id)
        )
        self._console_short = abbreviate_console(console_name or f"Console #{installed_rom.console_id}")
        self._refresh_cover()

        console_text = console_name or f"Console #{installed_rom.console_id}"
        console_short = abbreviate_console(console_text)
        title = derive_title_from_filename(installed_rom.file_path)
        self.setToolTip(f"{title} ({console_text}) — click to play")

        margin = max(MIN_MARGIN, round(edge * MARGIN_RATIO))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(margin)
        layout.addWidget(self._cover_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        if edge >= CAPTION_MIN_COVER:
            title_label = QLabel()
            title_label.setAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            )
            title_label.ensurePolished()
            metrics = QFontMetrics(title_label.font())
            available = edge - CAPTION_SIDE_PAD
            lines = wrap_lines(title, metrics, available, MAX_TITLE_LINES)
            lines += wrap_lines(console_short, metrics, available, 1)
            title_label.setText("\n".join(lines))
            title_label.setFixedSize(edge, metrics.lineSpacing() * CAPTION_LINES)
            layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Only where the neighbouring cards have one. This widget appears in
        # two grids with different shapes: Continue Playing's cards carry a
        # progress bar, the Library's are art only. Adding it unconditionally
        # matched one and broke the other. An unmatched ROM never has real
        # progress — nothing knows which game it is — so the bar sits at zero
        # and says so; the point is that the row stays uniform.
        if show_progress:
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setFixedHeight(PROGRESS_BAR_HEIGHT)
            progress_bar.setFixedWidth(edge)
            progress_bar.setFormat("" if edge < CAPTION_MIN_COVER else "No progress")
            layout.addWidget(progress_bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Independent of a catalog match: RVZ/WIA can supply artwork by disc ID.
        if image_loader is not None:
            image_loader.rom_image_ready.connect(self._on_rom_cover_ready)
            image_loader.request_rom(installed_rom, cover_game)

    def _on_rom_cover_ready(self, rom_id: int, pixmap) -> None:
        if rom_id != self.installed_rom.id:
            return
        if pixmap is None or pixmap.isNull():
            return
        # A manual choice made while the background request was pending wins.
        if not QPixmap(str(cached_local_cover_path(self.installed_rom.id))).isNull():
            return
        # Cropped to the square like the other cards — a QPushButton icon is
        # letterboxed inside its icon size otherwise, so a 4:3 cover would
        # come out visibly smaller than a square one beside it.
        self._cover_button.setIcon(QIcon(fill_square(pixmap, self._cover_size)))
        self._cover_button.setText("")

    def build_context_menu(self) -> QMenu:
        """Built but not shown, so it's testable — `QMenu.exec` is a blocking
        C++ call that can't be intercepted from Python, which is how the
        matched cards' menu stayed broken unnoticed."""
        menu = QMenu(self)
        pick_cover_action = menu.addAction(PICK_COVER_ACTION_TEXT)
        pick_cover_action.triggered.connect(self._on_pick_cover)
        remove_action = menu.addAction(REMOVE_ACTION_TEXT)
        remove_action.triggered.connect(
            lambda: self.remove_requested.emit(self.installed_rom.id)
        )
        return menu

    def _show_context_menu(self, position) -> None:
        self.build_context_menu().exec(self.mapToGlobal(position))

    def _refresh_cover(self) -> None:
        cover_path = cached_local_cover_path(self.installed_rom.id)
        pixmap = QPixmap(str(cover_path)) if cover_path.is_file() else QPixmap()
        if not pixmap.isNull():
            self._cover_button.setIcon(
                QIcon(fill_square(pixmap, self._cover_size))
            )
            self._cover_button.setText("")
        else:
            self._cover_button.setIcon(QIcon(console_placeholder(self._cover_size, self._console_short)))
            self._cover_button.setText("")

    def _on_pick_cover(self) -> None:
        source_path, _ = QFileDialog.getOpenFileName(
            self, "Select Cover Image", filter=IMAGE_FILE_FILTER
        )
        if not source_path:
            return

        pixmap = QPixmap(source_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Invalid image", "Couldn't read that file as an image.")
            return

        cover_path = cached_local_cover_path(self.installed_rom.id)
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(cover_path), "PNG")
        self._refresh_cover()
