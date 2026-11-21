"""Community event row for the Awards view's Events section — presentation-only.

The whole row is clickable and opens the event's page on
retroachievements.org. That works with no new plumbing because RA models
events as games: the catalog sync already stored each one's
`retroachievements_url` through the same template every other game uses, so
this is the identical `QDesktopServices.openUrl` one-liner as the
"Open on RetroAchievements".

Deliberately not shown: end dates. RA's API doesn't expose them, and the
only other source would be scraping the forum, which this project doesn't do.
"""

from typing import Optional

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from retrocheevos.gui import styles
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.services.events_service import EventWithProgress

ICON_SIZE = QSize(40, 40)
NEW_BADGE_COLOR = styles.LINK
PROGRESS_COLOR = styles.TEXT_DIM


class EventRow(QFrame):
    def __init__(
        self,
        entry: EventWithProgress,
        image_loader: ImageLoader,
        is_new: bool = False,
    ) -> None:
        super().__init__()
        self.entry = entry
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this event on RetroAchievements")

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(ICON_SIZE)
        image_loader.image_ready.connect(self._on_image_ready)
        image_loader.request(entry.game)

        title_text = entry.game.title
        if is_new:
            title_text = f"{title_text}  •  NEW"
        title_label = QLabel(title_text)
        title_label.setWordWrap(True)
        if is_new:
            title_label.setStyleSheet(f"color: {NEW_BADGE_COLOR}; font-weight: bold;")

        progress_label = QLabel(self._progress_text())
        progress_label.setStyleSheet(f"color: {PROGRESS_COLOR};")

        info_column = QVBoxLayout()
        info_column.setSpacing(0)
        info_column.addWidget(title_label)
        info_column.addWidget(progress_label)

        content_row = QHBoxLayout(self)
        content_row.setContentsMargins(2, 4, 2, 4)
        content_row.addWidget(self._icon_label)
        content_row.addLayout(info_column, stretch=1)

    def _progress_text(self) -> str:
        if self.entry.achievements_total is None:
            # Progress hasn't been fetched yet — distinct from "fetched and
            # you haven't started", which is 0/N.
            return "Progress not synced yet"
        return f"{self.entry.achievements_unlocked or 0}/{self.entry.achievements_total} achievements"

    def _on_image_ready(self, game_id: int, pixmap: Optional[QPixmap]) -> None:
        if game_id != self.entry.game.id or pixmap is None:
            return
        self._icon_label.setPixmap(
            pixmap.scaled(
                ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt override
        url = self.entry.game.retroachievements_url
        if url:
            QDesktopServices.openUrl(QUrl(url))
        super().mouseReleaseEvent(event)
