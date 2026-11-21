"""One row of Home's Continue Playing list (R19, reviewed Home board).

Cover, title, console, progress and a guarded Play button. Progress uses
RetroAchievements' combined count, labeled "achievements" (D8); unknown
progress is never shown as zero. Matched games and unmatched ROMs share the
row: an unmatched ROM says so and keeps its cover and removal actions in a
"⋯" menu.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QProgressBar,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from retrocheevos.gui import styles
from retrocheevos.gui.components import CoverArt, button, text_label
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.library.console_names import abbreviate_console
from retrocheevos.library.local_covers import cached_local_cover_path
from retrocheevos.library.rom_title import derive_title_from_filename
from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom

COVER_EDGE = 56
PROGRESS_HEIGHT = 6
PROGRESS_UNAVAILABLE = "Progress unavailable"
NO_MATCH_TEXT = "No catalog match · progress unavailable"
NO_EMULATOR_REASON = "Configure an emulator in Settings"
IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
PICK_COVER_ACTION_TEXT = "Choose cover…"
REMOVE_ACTION_TEXT = "Remove from Library"


def progress_text(
    unlocked: Optional[int], total: Optional[int], percent: Optional[float]
) -> tuple[str, Optional[float]]:
    """The progress caption and bar fraction (None hides the bar)."""
    if unlocked is not None and total:
        unlocked = max(0, min(unlocked, total))
        return f"{unlocked}/{total} achievements", unlocked / total
    if percent is not None:
        return f"{percent:.0f}% complete", max(0.0, min(percent, 100.0)) / 100
    return PROGRESS_UNAVAILABLE, None


class ContinuePlayingRow(QFrame):
    """A matched game (`game`) or an unmatched ROM (`rom`), never both."""

    play_requested = Signal(int)  # game id, or installed ROM id for `rom`
    remove_requested = Signal(int)  # installed ROM id (unmatched only)

    def __init__(
        self,
        image_loader: ImageLoader,
        *,
        console_name: Optional[str],
        game: Optional[Game] = None,
        rom: Optional[InstalledRom] = None,
        cover_game: Optional[Game] = None,
        achievements_unlocked: Optional[int] = None,
        achievements_total: Optional[int] = None,
        percent_complete: Optional[float] = None,
        play_unavailable_reason: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if (game is None) == (rom is None):
            raise ValueError("pass exactly one of game or rom")
        self.game = game
        self.rom = rom
        self.setProperty("surface", "row")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        console = console_name or (
            f"Console #{(game or rom).console_id}"
        )
        self.title = game.title if game is not None else derive_title_from_filename(rom.file_path)
        self.cover = CoverArt(COVER_EDGE, abbreviate_console(console))

        title = QLabel()
        title.setStyleSheet("font-weight: 600;")
        title.setToolTip(self.title)
        self._title_label = title
        console_label = text_label(console, "secondary")

        if game is not None:
            caption, fraction = progress_text(achievements_unlocked, achievements_total, percent_complete)
        else:
            caption, fraction = NO_MATCH_TEXT, None
        self._progress_label = text_label(caption, "secondary")
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(PROGRESS_HEIGHT)
        self._bar.setRange(0, 1000)
        self._bar.setValue(round((fraction or 0) * 1000))
        self._bar.setVisible(fraction is not None)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addWidget(title)
        text.addWidget(console_label)
        text.addWidget(self._bar)
        text.addWidget(self._progress_label)
        # Shown as text, not only as a tooltip: disabled buttons don't show
        # tooltips everywhere, and the user needs the next step.
        self._reason_label = text_label(play_unavailable_reason or "", "secondary")
        self._reason_label.setVisible(play_unavailable_reason is not None)
        text.addWidget(self._reason_label)

        self._play = button("Play", "primary", compact=True)
        self._play.clicked.connect(self._emit_play)
        self._play.setEnabled(play_unavailable_reason is None)
        self._play.setToolTip(play_unavailable_reason or f"Play {self.title}")
        self._play.setAccessibleName(f"Play {self.title}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(styles.SPACE_S, styles.SPACE_S, styles.SPACE_M, styles.SPACE_S)
        layout.setSpacing(styles.SPACE_M)
        layout.addWidget(self.cover)
        layout.addLayout(text, stretch=1)
        layout.addWidget(self._play)
        if rom is not None:
            more = QPushButton("⋯")
            more.setProperty("size", "compact")
            more.setFixedWidth(40)
            more.setToolTip("More actions")
            more.setAccessibleName(f"More actions for {self.title}")
            more.clicked.connect(lambda: self.build_menu().popup(more.mapToGlobal(QPoint(0, more.height()))))
            layout.addWidget(more)

        self.setAccessibleName(f"{self.title}, {console}, {caption}")

        if game is not None:
            image_loader.image_ready.connect(self._on_game_image)
            image_loader.request(game)
        else:
            if not self._apply_local_cover():
                image_loader.rom_image_ready.connect(self._on_rom_image)
                image_loader.request_rom(rom, cover_game)

    # Text ----------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self._elide_title()

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self._elide_title()

    def _elide_title(self) -> None:
        width = max(40, self._title_label.width())
        metrics = QFontMetrics(self._title_label.font())
        self._title_label.setText(metrics.elidedText(self.title, Qt.TextElideMode.ElideRight, width))

    def progress_caption(self) -> str:
        return self._progress_label.text()

    def bar_visible(self) -> bool:
        return not self._bar.isHidden()

    def play_enabled(self) -> bool:
        return self._play.isEnabled()

    def play_unavailable_reason(self) -> str:
        return self._reason_label.text() if not self._reason_label.isHidden() else ""

    # Actions ---------------------------------------------------------------

    def _emit_play(self) -> None:
        self.play_requested.emit(self.game.id if self.game is not None else self.rom.id)

    def build_menu(self) -> QMenu:
        """Unmatched ROM actions; built separately from showing for tests."""
        menu = QMenu(self)
        menu.addAction(PICK_COVER_ACTION_TEXT, self._on_pick_cover)
        menu.addAction(REMOVE_ACTION_TEXT, lambda: self.remove_requested.emit(self.rom.id))
        return menu

    def _on_pick_cover(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Select Cover Image", filter=IMAGE_FILE_FILTER)
        if not source:
            return
        pixmap = QPixmap(source)
        if pixmap.isNull():
            QMessageBox.warning(self, "Invalid image", "Couldn't read that file as an image.")
            return
        destination = cached_local_cover_path(self.rom.id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(destination), "PNG")
        self._apply_local_cover()

    # Artwork ---------------------------------------------------------------

    def _apply_local_cover(self) -> bool:
        pixmap = QPixmap(str(cached_local_cover_path(self.rom.id)))
        if pixmap.isNull():
            return False
        self.cover.set_cover(pixmap)
        return True

    def _on_game_image(self, game_id: int, pixmap) -> None:
        if game_id == self.game.id:
            self.cover.set_cover(pixmap)

    def _on_rom_image(self, rom_id: int, pixmap) -> None:
        if rom_id != self.rom.id:
            return
        # A manual cover chosen while the request was pending wins.
        if not QPixmap(str(cached_local_cover_path(self.rom.id))).isNull():
            return
        self.cover.set_cover(pixmap)
