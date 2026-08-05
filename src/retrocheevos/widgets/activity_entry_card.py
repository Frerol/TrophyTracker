"""Recent Activity feed row widget (UI.md — Home screen, RA "Following"-
page style). Presentation-only (Architecture.md §3.1), built from an
already-fetched `ActivityEntry` — no service/API calls of its own. No
Message/Unfollow/Block buttons — this section has no social actions.

A plain widget added to a `QVBoxLayout` inside a `QScrollArea`, not
`QListWidget.setItemWidget()` or any other `QAbstractItemView`
widget-embedding — `DevelopmentRoadmap.md`'s `RemovableListDelegate` note
documents that mechanism as implicated in a real native crash this
project hit, avoided ever since even at small scale. This mirrors the
already-proven Continue Playing pattern in `gui/pages/home_page.py`
instead (real widgets in a plain container layout).
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from retrocheevos.models.activity_feed import ActivityEntry

AVATAR_SIZE = 48
GAME_ICON_SIZE = 24
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60

# Distinct from the card's other text, matching the differently-colored
# status line on RA's own Following page.
STATUS_TEXT_COLOR = "#8a63d2"


class ActivityEntryCard(QFrame):
    def __init__(self, entry: ActivityEntry) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.Box)

        avatar_label = QLabel()
        avatar_label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        _set_pixmap(avatar_label, entry.avatar_path, AVATAR_SIZE)

        username_label = QLabel(entry.username)
        username_font = username_label.font()
        username_font.setBold(True)
        username_label.setFont(username_font)

        text_column = QVBoxLayout()
        text_column.addWidget(username_label)

        if entry.last_achievement_at is not None:
            text_column.addWidget(
                QLabel(f"Last activity: {entry.last_achievement_at:%Y-%m-%d %H:%M}")
            )

        if entry.game_title is not None:
            game_row = QHBoxLayout()
            game_icon_label = QLabel()
            game_icon_label.setFixedSize(GAME_ICON_SIZE, GAME_ICON_SIZE)
            _set_pixmap(game_icon_label, entry.game_icon_path, GAME_ICON_SIZE)
            game_row.addWidget(game_icon_label)
            game_text = entry.game_title
            if entry.game_console:
                game_text += f" — {entry.game_console}"
            game_row.addWidget(QLabel(game_text))
            game_row.addStretch(1)
            text_column.addLayout(game_row)

        if entry.achievements_total is not None:
            text_column.addWidget(QLabel(_format_progress(entry)))

        status_label = QLabel(entry.status_text)
        status_label.setStyleSheet(f"color: {STATUS_TEXT_COLOR};")
        text_column.addWidget(status_label)

        layout = QHBoxLayout(self)
        layout.addWidget(avatar_label)
        layout.addLayout(text_column, stretch=1)


def _set_pixmap(label: QLabel, path: Optional[Path], size: int) -> None:
    if path is None:
        return
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return
    label.setPixmap(
        pixmap.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    )


def _format_progress(entry: ActivityEntry) -> str:
    text = f"{entry.achievements_unlocked}/{entry.achievements_total} achievements"
    if entry.playtime_seconds:
        hours, remainder = divmod(entry.playtime_seconds, SECONDS_PER_HOUR)
        minutes = remainder // SECONDS_PER_MINUTE
        text += f" | Played {hours}h{minutes:02d}m"
    return text
