"""Shared interface components for the revamp (roadmap R17).

Each component is a thin Qt widget whose look comes from `gui/styles.py`
through object names and dynamic properties, so screens stay consistent and a
token change restyles every screen. The components encode the product rules
from `docs/design/ScreenDataMapping.md`:

* unknown values are shown as unavailable, never as zero;
* hardcore and softcore progress are separate and always labeled;
* state is carried by text, not by color alone.

`GameCard` and `AchievementRow` are widgets for short lists (Home's Continue
Playing, a game's achievement list). Large grids, such as Library, must paint
with a model/view delegate that uses the same tokens instead of creating one
widget per item (R07 budget, R22).
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.gui import styles

UNKNOWN_VALUE = '—'
PROGRESS_UNAVAILABLE = 'Progress unavailable'

MODE_HARDCORE = 'hardcore'
MODE_SOFTCORE = 'softcore'
_MODE_LABELS = {MODE_HARDCORE: 'Hardcore', MODE_SOFTCORE: 'Softcore'}

STATE_LOCKED = 'locked'
STATE_HARDCORE = 'hardcore'
STATE_SOFTCORE = 'softcore'
_STATE_LABELS = {
    STATE_LOCKED: 'Locked',
    STATE_HARDCORE: 'Unlocked · Hardcore',
    STATE_SOFTCORE: 'Unlocked · Softcore',
}


def _repolish(widget: QWidget) -> None:
    """Re-evaluate stylesheet selectors after a dynamic property changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_property(widget: QWidget, name: str, value) -> None:
    widget.setProperty(name, value)
    _repolish(widget)


# --- Text -------------------------------------------------------------------

def text_label(text: str = '', role: Optional[str] = None, *, wrap: bool = False) -> QLabel:
    """A plain-text label with a typography role: pageTitle, sectionTitle,
    metric, secondary, caption, points or error."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    if role:
        label.setProperty('role', role)
    return label


def page_title(text: str) -> QLabel:
    label = text_label(text, 'pageTitle')
    label.setAccessibleName(text)
    return label


def section_title(text: str) -> QLabel:
    return text_label(text, 'sectionTitle')


class StatusPill(QLabel):
    """A short status label. Kinds: neutral, hardcore, softcore, mastered, error."""

    def __init__(self, text: str, kind: str = 'neutral', parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setProperty('pill', kind)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_status(self, text: str, kind: str) -> None:
        self.setText(text)
        set_property(self, 'pill', kind)


# --- Buttons and inputs -----------------------------------------------------

def button(text: str, variant: str = 'secondary', *, compact: bool = False,
           parent: Optional[QWidget] = None) -> QPushButton:
    """Variants: primary (gold), secondary (default), ghost, danger."""
    widget = QPushButton(text, parent)
    if variant != 'secondary':
        widget.setProperty('variant', variant)
    if compact:
        widget.setProperty('size', 'compact')
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


class FilterChip(QPushButton):
    """A checkable pill used for filters."""

    def __init__(self, text: str, checked: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setProperty('chip', True)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class SidebarItem(QPushButton):
    """A checkable navigation entry for the sidebar."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName('sidebarItem')
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)


class SearchField(QLineEdit):
    """A rounded search input with a clear button."""

    def __init__(self, placeholder: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty('search', True)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setAccessibleName(placeholder)


# --- Progress ---------------------------------------------------------------

class ModeProgress(QWidget):
    """Achievement progress for one mode: a labeled bar plus "X/Y" text.

    `set_progress(None, None)` shows "Progress unavailable" instead of an
    empty bar, so unknown is never displayed as zero.
    """

    def __init__(self, mode: str = MODE_HARDCORE, *, show_mode: bool = True,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._show_mode = show_mode
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(styles.SPACE_XS)
        self._label = text_label('', 'secondary')
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setProperty('mode', mode)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)
        self.set_progress(None, None)

    def set_progress(self, unlocked: Optional[int], total: Optional[int]) -> None:
        prefix = f'{_MODE_LABELS.get(self._mode, self._mode)} · ' if self._show_mode else ''
        if unlocked is None or not total:
            self._label.setText(prefix + PROGRESS_UNAVAILABLE)
            self._bar.setVisible(False)
            self.setAccessibleName(prefix + PROGRESS_UNAVAILABLE)
            return
        unlocked = max(0, min(unlocked, total))
        text = f'{prefix}{unlocked}/{total} achievements'
        self._label.setText(text)
        self._bar.setRange(0, total)
        self._bar.setValue(unlocked)
        self._bar.setVisible(True)
        self.setAccessibleName(text)

    def label_text(self) -> str:
        return self._label.text()

    def bar_visible(self) -> bool:
        return not self._bar.isHidden()


# --- Cards and rows ---------------------------------------------------------

class MetricCard(QFrame):
    """A large number with a caption. `None` shows the unknown marker."""

    def __init__(self, label: str, caption: str = '', parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty('surface', 'panel')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(styles.GAP, styles.GAP, styles.GAP, styles.GAP)
        layout.setSpacing(styles.SPACE_XS)
        self._label = text_label(label, 'caption')
        self._value = text_label(UNKNOWN_VALUE, 'metric')
        self._caption = text_label(caption, 'secondary', wrap=True)
        self._default_caption = caption
        for widget in (self._label, self._value, self._caption):
            layout.addWidget(widget)
        self._name = label
        self.set_value(None)

    def set_value(self, value: Optional[int], *, unavailable_caption: str = 'Not synced yet') -> None:
        if value is None:
            self._value.setText(UNKNOWN_VALUE)
            self._caption.setText(unavailable_caption)
            self.setAccessibleName(f'{self._name}: unavailable')
            return
        self._value.setText(f'{value:,}')
        self._caption.setText(self._default_caption)
        self.setAccessibleName(f'{self._name}: {value:,}')

    def value_text(self) -> str:
        return self._value.text()


class CoverArt(QLabel):
    """A rounded cover slot that shows a pixmap or a text fallback."""

    def __init__(self, edge: int = 96, fallback: str = '', parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(edge, edge)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty('role', 'secondary')
        self.setStyleSheet(
            f'background: {styles.SURFACE_RAISED}; border-radius: {styles.RADIUS_COVER}px;'
        )
        self.set_fallback(fallback)

    def set_fallback(self, text: str) -> None:
        self.setPixmap(QPixmap())
        self.setText(text)

    def set_cover(self, pixmap: Optional[QPixmap]) -> None:
        if pixmap is None or pixmap.isNull():
            return
        self.setText('')
        self.setPixmap(pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        ))


class GameCard(QFrame):
    """Cover, title, console, progress and a guarded Play action.

    `play_unavailable_reason` disables Play and shows why (for example
    "Configure an emulator"), so a missing prerequisite is actionable rather
    than a silent dead button.
    """

    play_requested = Signal()

    def __init__(self, title: str, console: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty('surface', 'card')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(styles.SPACE_M, styles.SPACE_M, styles.SPACE_M, styles.SPACE_M)
        layout.setSpacing(styles.SPACE_S)
        self.cover = CoverArt(160, console)
        layout.addWidget(self.cover, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._title = text_label(title, wrap=True)
        self._title.setStyleSheet('font-weight: 600;')
        layout.addWidget(self._title)
        layout.addWidget(text_label(console, 'secondary'))
        self.progress = ModeProgress(MODE_HARDCORE, show_mode=False)
        layout.addWidget(self.progress)
        self._play = button('Play', 'primary', compact=True)
        self._play.clicked.connect(self.play_requested)
        self._reason = text_label('', 'secondary', wrap=True)
        self._reason.setVisible(False)
        layout.addWidget(self._play)
        layout.addWidget(self._reason)
        self.setAccessibleName(f'{title}, {console}')

    def set_progress(self, unlocked: Optional[int], total: Optional[int]) -> None:
        self.progress.set_progress(unlocked, total)

    def set_play_unavailable(self, reason: Optional[str]) -> None:
        self._play.setEnabled(reason is None)
        self._reason.setText(reason or '')
        self._reason.setVisible(reason is not None)

    def play_enabled(self) -> bool:
        return self._play.isEnabled()


class AchievementRow(QFrame):
    """Badge, title, description, points and a text state pill."""

    def __init__(self, title: str, description: str, points: int,
                 state: str = STATE_LOCKED, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty('surface', 'row')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(styles.SPACE_S, styles.SPACE_M, styles.SPACE_S, styles.SPACE_M)
        layout.setSpacing(styles.SPACE_M)
        self.badge = CoverArt(48, '')
        layout.addWidget(self.badge)
        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        name = text_label(title)
        name.setStyleSheet('font-weight: 600;')
        text_column.addWidget(name)
        text_column.addWidget(text_label(description, 'secondary', wrap=True))
        layout.addLayout(text_column, stretch=1)
        layout.addWidget(text_label(f'{points} pts', 'points'))
        self.pill = StatusPill('')
        layout.addWidget(self.pill)
        self._title = title
        self.set_state(state)

    def set_state(self, state: str) -> None:
        kind = state if state in (STATE_HARDCORE, STATE_SOFTCORE) else 'neutral'
        label = _STATE_LABELS.get(state, _STATE_LABELS[STATE_LOCKED])
        self.pill.set_status(label, kind)
        self.setAccessibleName(f'{self._title}: {label}')
