"""A one-line "there's a newer version" strip, shown above the header.

Notify-only, matching `services/update_service.py`: a sentence, a link to the
release, and an "x". Nothing here downloads or installs.

Hidden by default and only shown once the check comes back positive, so an
app that is up to date — or offline — never reserves space for it.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from retrocheevos.gui import styles

DISMISS_TOOLTIP = "Don't remind me about this version again"
BANNER_PADDING_V = 6
BANNER_PADDING_H = 10
DISMISS_BUTTON_SIZE = 20


class UpdateBanner(QFrame):
    dismissed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setVisible(False)

        # `setOpenExternalLinks`, not a clicked handler: Qt hands the URL to
        # the system browser itself, so nothing here has to shell out.
        self._message = QLabel()
        self._message.setOpenExternalLinks(True)
        self._message.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )

        dismiss_button = QPushButton("×")
        dismiss_button.setToolTip(DISMISS_TOOLTIP)
        dismiss_button.setFixedSize(DISMISS_BUTTON_SIZE, DISMISS_BUTTON_SIZE)
        dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_button.clicked.connect(self._on_dismiss)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            BANNER_PADDING_H, BANNER_PADDING_V, BANNER_PADDING_H, BANNER_PADDING_V
        )
        layout.addWidget(self._message, stretch=1)
        layout.addWidget(dismiss_button)

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {styles.BOX_BG};
                border: 1px solid {styles.LINK};
                border-radius: {styles.RADIUS}px;
            }}
            QLabel {{ border: none; color: {styles.TEXT}; }}
            QPushButton {{
                border: none;
                color: {styles.TEXT_DIM};
                background: transparent;
            }}
            QPushButton:hover {{ color: {styles.LINK_HOVER}; }}
            """
        )

    def show_update(self, version: str, url: str) -> None:
        # `version` comes from a GitHub release tag, i.e. from outside the
        # app, and this label renders rich text — so it is escaped rather
        # than interpolated raw. `url` goes in an href for the same reason:
        # only ever into the attribute, never built into markup by hand.
        safe_version = _escape(version)
        safe_url = _escape(url)
        self._message.setText(
            f'Version <b>{safe_version}</b> is available — '
            f'<a href="{safe_url}" style="color: {styles.LINK};">'
            f"see what's new</a>"
        )
        self.setVisible(True)

    def _on_dismiss(self) -> None:
        self.setVisible(False)
        self.dismissed.emit()


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
