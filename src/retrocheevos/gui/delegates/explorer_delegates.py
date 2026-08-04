"""Explorer table delegates (UI.md 3.2) — presentation-only (Architecture.md
§3.1). Three custom `QStyledItemDelegate`s: Title (icon + text), Progress
(a painted progress-bar look), and Actions (painted Play/+/Follow buttons)
— none of them use a real embedded widget, consistent with why the table
uses `QTableView` at all: no per-cell widgets to construct, so nothing to
virtualize by hand. `ActionsDelegate` specifically replaces an earlier
`QTableView.setIndexWidget()`-based implementation
(`widgets/explorer_row_actions.py`, removed): multiple independent Qt/
PySide bug reports describe real widgets embedded in a virtualized view via
`setIndexWidget()` as fragile, and this app hit a matching native crash
(`STATUS_FATAL_USER_CALLBACK_EXCEPTION` inside `Qt6Widgets.dll`, reproduced
across two PySide6 versions) specifically on the Explorer page. Every other
column uses the default text delegate, no customization needed.
"""

from typing import Optional

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionProgressBar,
    QStyleOptionViewItem,
)

from retrocheevos.utils.enums import ListType

ICON_SIZE = 32
ICON_MARGIN = 6
PLACEHOLDER_COLOR = Qt.GlobalColor.darkGray

# Row-scoped (not column-scoped, unlike COLUMN_PROGRESS's plain UserRole):
# `ExplorerTableModel` returns the row's game id for this role regardless
# of which column is asked, so `ActionsDelegate` can read it without
# reaching into the model's Python API directly — keeps the delegate a
# pure presentation layer, like `TitleDelegate`/`ProgressDelegate`.
GAME_ID_ROLE = Qt.ItemDataRole.UserRole + 2


class TitleDelegate(QStyledItemDelegate):
    """Draws a cover-art thumbnail (or a neutral placeholder while/if it
    isn't loaded — see `ExplorerTableModel._pixmap_for`) followed by the
    game title.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))
            text_color = option.palette.color(QPalette.ColorRole.HighlightedText)
        else:
            text_color = option.palette.color(QPalette.ColorRole.Text)

        icon_rect = QRect(
            option.rect.left() + ICON_MARGIN,
            option.rect.top() + (option.rect.height() - ICON_SIZE) // 2,
            ICON_SIZE,
            ICON_SIZE,
        )
        # Pre-scaled to ICON_SIZE by `ExplorerTableModel._on_image_ready` —
        # drawn as-is here, not re-scaled on every paint.
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(icon_rect, pixmap)
        else:
            painter.fillRect(icon_rect, PLACEHOLDER_COLOR)

        text_rect = QRect(
            icon_rect.right() + ICON_MARGIN,
            option.rect.top(),
            option.rect.right() - icon_rect.right() - 2 * ICON_MARGIN,
            option.rect.height(),
        )
        painter.setPen(text_color)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data(Qt.ItemDataRole.DisplayRole) or "",
        )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(base.height(), ICON_SIZE + 2 * ICON_MARGIN))


class ProgressDelegate(QStyledItemDelegate):
    """Paints a progress bar for rows with known completion; falls back to
    the default text delegate ("—") when the account has no tracked
    progress for that game (`ExplorerTableModel`'s `UserRole` is `None`).
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        percent = index.data(Qt.ItemDataRole.UserRole)
        if percent is None:
            super().paint(painter, option, index)
            return

        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))

        progress_option = QStyleOptionProgressBar()
        progress_option.rect = option.rect.adjusted(4, 4, -4, -4)
        progress_option.minimum = 0
        progress_option.maximum = 100
        progress_option.progress = round(percent)
        progress_option.text = f"{percent:.0f}%"
        progress_option.textVisible = True

        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ProgressBar, progress_option, painter, option.widget
        )
        painter.restore()


# Duplicated from the removed `widgets/explorer_row_actions.py` rather than
# imported from a shared module — same small-duplication precedent as
# `widgets/game_card.py`'s own copy of this mapping.
LIST_ACTION_LABELS = {
    ListType.WANT_TO_PLAY: "Want to Play",
    ListType.PLAYING: "Playing",
    ListType.ABANDONED: "Abandoned",
    ListType.FOLLOWING: "Following",
}

# Kept separate from LIST_ACTION_LABELS (rendered after a separator in
# _show_menu) — hiding a game everywhere is a different kind of action than
# progress-tracking list membership, same reasoning as the separator
# `widgets/game_card.py` already puts before "Open on RetroAchievements".
BLOCK_ACTION_LABEL = "Block"

_ACTION_BUTTON_SPECS = [("play", "Play"), ("follow", "Follow"), ("menu", "+")]
_BUTTON_MARGIN = 4
_BUTTON_SPACING = 4


class ActionsDelegate(QStyledItemDelegate):
    """Paints Play/+/Follow as native-styled buttons (`QStyle.CE_PushButton`,
    no real `QPushButton`) and detects clicks via `editorEvent` — the same
    widget-less-interactivity mechanism Qt's own checkbox delegates use.
    Replaces an earlier `QTableView.setIndexWidget()`-based implementation;
    see this module's docstring for why.

    v1 deliberately skips per-button hover highlighting: that needs the
    view to forward every `mouseMoveEvent` at sub-cell granularity, which
    means subclassing `QTableView` — real added surface area for a change
    whose actual goal is removing crash risk, not chasing pixel-perfect
    native fidelity. Buttons still show `Sunken` press feedback (needs no
    mouse-tracking) and are fully clickable.
    """

    play_requested = Signal(int)  # game_id
    list_action_requested = Signal(int, object)  # game_id, ListType
    follow_requested = Signal(int)  # game_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pressed: Optional[tuple[QPersistentModelIndex, str]] = None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))

        style = option.widget.style() if option.widget else QApplication.style()
        persistent_index = QPersistentModelIndex(index)
        for key, label, rect in self._button_rects(option):
            button_option = QStyleOptionButton()
            button_option.rect = rect
            button_option.text = label
            button_option.palette = option.palette
            button_option.fontMetrics = option.fontMetrics
            button_option.state = QStyle.StateFlag.State_Enabled
            button_option.state |= (
                QStyle.StateFlag.State_Sunken
                if self._pressed == (persistent_index, key)
                else QStyle.StateFlag.State_Raised
            )
            style.drawControl(QStyle.ControlElement.CE_PushButton, button_option, painter, option.widget)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        style = option.widget.style() if option.widget else QApplication.style()
        total_width = 2 * _BUTTON_MARGIN + _BUTTON_SPACING * (len(_ACTION_BUTTON_SPECS) - 1)
        max_height = 0
        for _key, label in _ACTION_BUTTON_SPECS:
            size = self._content_size(option, style, label)
            total_width += size.width()
            max_height = max(max_height, size.height())
        return QSize(total_width, max_height + 2 * _BUTTON_MARGIN)

    def editorEvent(
        self, event: QEvent, model, option: QStyleOptionViewItem, index: QModelIndex
    ) -> bool:
        if event.type() not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            return False

        persistent_index = QPersistentModelIndex(index)
        pos = event.position().toPoint()
        key = self._button_at(option, pos)

        if event.type() == QEvent.Type.MouseButtonPress:
            if key is None:
                return False
            self._pressed = (persistent_index, key)
            self._repaint_cell(option)
            return True

        # MouseButtonRelease: only counts as a click if it lands on the same
        # button that was pressed — matches normal button click semantics
        # (press, drag off, release elsewhere = no click).
        pressed = self._pressed
        self._pressed = None
        self._repaint_cell(option)
        if pressed is None or pressed != (persistent_index, key):
            return False

        game_id = index.data(GAME_ID_ROLE)
        if game_id is None:
            return False
        if key == "play":
            self.play_requested.emit(game_id)
        elif key == "follow":
            self.follow_requested.emit(game_id)
        elif key == "menu":
            self._show_menu(option, game_id)
        return True

    def _content_size(self, option: QStyleOptionViewItem, style: QStyle, label: str) -> QSize:
        button_option = QStyleOptionButton()
        button_option.state = QStyle.StateFlag.State_Enabled
        button_option.text = label
        button_option.fontMetrics = option.fontMetrics
        text_size = option.fontMetrics.size(Qt.TextFlag.TextShowMnemonic, label)
        return style.sizeFromContents(
            QStyle.ContentsType.CT_PushButton, button_option, text_size, option.widget
        )

    def _button_rects(self, option: QStyleOptionViewItem) -> list[tuple[str, str, QRect]]:
        style = option.widget.style() if option.widget else QApplication.style()
        rects: list[tuple[str, str, QRect]] = []
        x = option.rect.left() + _BUTTON_MARGIN
        center_y = option.rect.top() + option.rect.height() // 2
        for key, label in _ACTION_BUTTON_SPECS:
            size = self._content_size(option, style, label)
            rect = QRect(x, center_y - size.height() // 2, size.width(), size.height())
            rects.append((key, label, rect))
            x += size.width() + _BUTTON_SPACING
        return rects

    def _button_at(self, option: QStyleOptionViewItem, pos) -> Optional[str]:
        for key, _label, rect in self._button_rects(option):
            if rect.contains(pos):
                return key
        return None

    def _repaint_cell(self, option: QStyleOptionViewItem) -> None:
        if option.widget:
            option.widget.update(option.rect)

    def _show_menu(self, option: QStyleOptionViewItem, game_id: int) -> None:
        menu_rect = next(rect for key, _label, rect in self._button_rects(option) if key == "menu")
        menu = QMenu(option.widget)
        for list_type, label in LIST_ACTION_LABELS.items():
            action = menu.addAction(label)
            action.triggered.connect(self._make_list_action_handler(game_id, list_type))
        menu.addSeparator()
        block_action = menu.addAction(BLOCK_ACTION_LABEL)
        block_action.triggered.connect(self._make_list_action_handler(game_id, ListType.BLOCKED))
        anchor = menu_rect.bottomLeft()
        global_pos = option.widget.mapToGlobal(anchor) if option.widget else anchor
        menu.exec(global_pos)

    def _make_list_action_handler(self, game_id: int, list_type: ListType):
        return lambda: self.list_action_requested.emit(game_id, list_type)
