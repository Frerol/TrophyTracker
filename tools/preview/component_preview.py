"""Component preview for the R17 visual system.

Shows every shared component from `gui/components.py` in its static states,
the color tokens with their contrast ratios, the type scale, and the brand
concept size comparison. All data is synthetic.

Usage (from the repository root)::

    PYTHONPATH=src .venv/bin/python tools/preview/component_preview.py
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python \\
        tools/preview/component_preview.py --screenshot components.png
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python \\
        tools/preview/component_preview.py --brand-sheet brand-sheet.png

Hover and pressed states are visible only in the interactive window. The
screenshot shows default, checked/selected, focused, disabled and error states.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.gui import components as c
from retrocheevos.gui import styles

ROOT = Path(__file__).resolve().parents[2]
BRAND_DIR = ROOT / 'docs' / 'design' / 'brand-exploration'
BRAND_CONCEPTS = (
    ('A · Pixel trophy', 'concept-a-pixel-trophy.svg'),
    ('C · Cartridge and pixel trophy', 'concept-c-cartridge-trophy.svg'),
    ('B · Trophy and D-pad (alternative)', 'concept-b-trophy-dpad.svg'),
)
BRAND_SIZES = (16, 24, 32, 48, 64, 128)
# Taskbars and docks can be dark or light, so icons are compared on both.
BRAND_BACKGROUNDS = (('Dark taskbar', styles.SURFACE_SIDEBAR), ('Light taskbar', '#F3F3F3'))
PREVIEW_WIDTH = 1240


def _row(*widgets: QWidget, stretch: bool = True) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(styles.SPACE_M)
    for widget in widgets:
        layout.addWidget(widget)
    if stretch:
        layout.addStretch(1)
    return holder


def _section(title: str, *rows: QWidget, note: str = '') -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, styles.SPACE_L, 0, 0)
    layout.setSpacing(styles.SPACE_M)
    layout.addWidget(c.section_title(title))
    if note:
        layout.addWidget(c.text_label(note, 'secondary', wrap=True))
    for row in rows:
        layout.addWidget(row)
    return panel


def _caption(text: str, widget: QWidget) -> QWidget:
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(styles.SPACE_XS)
    layout.addWidget(widget)
    layout.addWidget(c.text_label(text, 'caption'))
    return holder


def _typography() -> QWidget:
    return _section(
        'Typography',
        c.page_title('Page title · Space Grotesk 28'),
        c.section_title('Section title · Space Grotesk 16'),
        c.text_label('12,480', 'metric'),
        c.text_label('Body text · Inter 14. Supported accents: Pokémon, Mötley, Ōkami.'),
        c.text_label('Secondary text · Inter 13', 'secondary'),
        c.text_label('CAPTION · INTER 12', 'caption'),
    )


def _swatches() -> QWidget:
    grid_holder = QWidget()
    grid = QGridLayout(grid_holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(styles.SPACE_M)
    grid.setVerticalSpacing(styles.SPACE_S)
    for index, (name, value) in enumerate(styles.COLOR_TOKENS.items()):
        swatch = QLabel()
        swatch.setFixedSize(28, 28)
        swatch.setStyleSheet(f'background: {value}; border: 1px solid {styles.OUTLINE_CONTROL}; border-radius: 6px;')
        on_panel = styles.contrast_ratio(value, styles.SURFACE_PANEL)
        on_app = styles.contrast_ratio(value, styles.SURFACE_APP)
        text = c.text_label(f'{name}  {value}  ·  {on_panel:.2f}:1 panel  ·  {on_app:.2f}:1 app', 'secondary')
        row, column = divmod(index, 2)
        grid.addWidget(swatch, row, column * 2)
        grid.addWidget(text, row, column * 2 + 1)
    return _section('Color tokens', grid_holder,
                    note='Contrast against the panel and application surfaces. Text needs 4.5:1; '
                         'large text and control boundaries need 3:1.')


def _buttons() -> tuple[QWidget, QWidget]:
    rows = []
    focus_target = None
    for variant in ('primary', 'secondary', 'ghost', 'danger'):
        default = c.button(variant.title(), variant)
        compact = c.button('Compact', variant, compact=True)
        disabled = c.button('Disabled', variant)
        disabled.setEnabled(False)
        if variant == 'primary':
            focus_target = c.button('Focused', variant)
            rows.append(_row(default, compact, disabled, focus_target))
        else:
            rows.append(_row(default, compact, disabled))
    return _section('Buttons', *rows, note='Primary is gold; secondary is the default. '
                    'The "Focused" button shows the keyboard focus ring.'), focus_target


def _chips_and_navigation() -> QWidget:
    disabled_chip = c.FilterChip('Disabled')
    disabled_chip.setEnabled(False)
    chips = _row(c.FilterChip('All', checked=True), c.FilterChip('In progress'),
                 c.FilterChip('Mastered'), c.FilterChip('Unmatched'), disabled_chip)
    sidebar = QWidget()
    sidebar.setObjectName('sidebar')
    sidebar.setFixedWidth(styles.SIDEBAR_WIDTH)
    sidebar_layout = QVBoxLayout(sidebar)
    for name, checked, enabled in (('Home', True, True), ('Library', False, True),
                                   ('Lists', False, True), ('Settings', False, False)):
        item = c.SidebarItem(name)
        item.setChecked(checked)
        item.setEnabled(enabled)
        sidebar_layout.addWidget(item)
    return _section('Filter chips and navigation', chips, sidebar,
                    note='Sidebar: selected (Home), default, and disabled (Settings, shown for reference only).')


def _inputs() -> QWidget:
    empty = c.SearchField('Search your library')
    filled = c.SearchField('Search the catalog')
    filled.setText('Super Metroid')
    disabled = c.SearchField('Disabled search')
    disabled.setEnabled(False)
    invalid = QLineEdit('not-a-valid-key')
    invalid.setProperty('invalid', True)
    for field in (empty, filled, disabled, invalid):
        field.setFixedWidth(260)
    return _section('Search and inputs', _row(empty, filled), _row(disabled, _caption('Invalid value', invalid)))


def _progress_and_metrics() -> QWidget:
    hardcore = c.ModeProgress(c.MODE_HARDCORE)
    hardcore.set_progress(34, 42)
    softcore = c.ModeProgress(c.MODE_SOFTCORE)
    softcore.set_progress(21, 58)
    zero = c.ModeProgress(c.MODE_HARDCORE)
    zero.set_progress(0, 24)
    unknown = c.ModeProgress(c.MODE_HARDCORE)
    for widget in (hardcore, softcore, zero, unknown):
        widget.setFixedWidth(240)
    points = c.MetricCard('Points', 'Selected account')
    points.set_value(12480)
    beaten = c.MetricCard('Beaten games', 'RetroAchievements award status')
    beaten.set_value(27)
    unknown_metric = c.MetricCard('Mastered games', 'RetroAchievements award status')
    for card in (points, beaten, unknown_metric):
        card.setFixedWidth(240)
    pills = _row(c.StatusPill('Neutral'), c.StatusPill('Hardcore', 'hardcore'),
                 c.StatusPill('Softcore', 'softcore'), c.StatusPill('Mastered', 'mastered'),
                 c.StatusPill('Sync failed', 'error'))
    return _section('Progress, metrics and status', _row(hardcore, softcore, zero, unknown),
                    _row(points, beaten, unknown_metric), pills,
                    note='Zero progress (0/24) and unknown progress are different states. '
                         'Unknown metrics show "—" with a reason.')


def _cards_and_rows() -> QWidget:
    playable = c.GameCard('Super Metroid', 'Super Nintendo')
    playable.set_progress(34, 42)
    no_emulator = c.GameCard('Chrono Trigger', 'Super Nintendo')
    no_emulator.set_progress(21, 58)
    no_emulator.set_play_unavailable('Configure an emulator for Super Nintendo')
    unknown = c.GameCard('Example homebrew', 'NES')
    for card in (playable, no_emulator, unknown):
        card.setFixedWidth(210)
    rows = QWidget()
    rows_layout = QVBoxLayout(rows)
    rows_layout.setContentsMargins(0, 0, 0, 0)
    rows_layout.setSpacing(0)
    for title, description, points, state in (
        ('Morph Ball', 'Obtain the Morph Ball', 5, c.STATE_HARDCORE),
        ('First Boss', 'Defeat Kraid', 10, c.STATE_SOFTCORE),
        ('No Pause', 'Finish the game in under 3 hours', 50, c.STATE_LOCKED),
    ):
        rows_layout.addWidget(c.AchievementRow(title, description, points, state))
    rows.setFixedWidth(720)
    return _section('Game cards and achievement rows', _row(playable, no_emulator, unknown), rows,
                    note='Cards: playable, Play unavailable with a reason, and unknown progress. '
                         'Rows: unlocked hardcore, unlocked softcore, locked.')


def _menus_and_dialogs(parent: QWidget) -> QWidget:
    menu_button = c.button('Open menu')
    menu = QMenu(menu_button)
    menu.addAction('Add to list…')
    menu.addAction('Open on RetroAchievements')
    menu.addSeparator()
    disabled_action = menu.addAction('Block game (disabled example)')
    disabled_action.setEnabled(False)
    menu_button.setMenu(menu)
    dialog_button = c.button('Open dialog')

    def show_dialog() -> None:
        QMessageBox.question(parent, 'Delete list', 'Delete "Backlog"? ROM files are not deleted.')

    dialog_button.clicked.connect(show_dialog)
    return _section('Menus and dialogs', _row(menu_button, dialog_button),
                    note='Interactive only: open them in the preview window.')


def render_svg(path: Path, edge: int) -> QPixmap:
    pixmap = QPixmap(edge, edge)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(path))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, edge, edge))
    painter.end()
    return pixmap


def build_brand_sheet() -> QPixmap:
    """A/C (and B) at taskbar and launcher sizes on dark and light backgrounds."""
    margin, label_width, cell = 24, 260, 140
    sheet_width = margin * 2 + label_width + cell * len(BRAND_SIZES)
    block_height = 40 + cell * len(BRAND_CONCEPTS)
    sheet = QPixmap(sheet_width, margin * 2 + 50 + block_height * len(BRAND_BACKGROUNDS) + 90)
    sheet.fill(QColor(styles.SURFACE_APP))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    title_font = QFont(styles.FONT_DISPLAY)
    title_font.setPixelSize(22)
    title_font.setBold(True)
    body_font = QFont(styles.FONT_UI)
    body_font.setPixelSize(13)
    painter.setFont(title_font)
    painter.setPen(QColor(styles.TEXT_PRIMARY))
    painter.drawText(margin, margin + 24, 'Brand concepts at icon sizes (decision D1)')
    y = margin + 50
    for background_name, background in BRAND_BACKGROUNDS:
        painter.fillRect(margin, y, sheet_width - margin * 2, block_height, QColor(background))
        light = background != styles.SURFACE_SIDEBAR
        painter.setPen(QColor('#202020' if light else styles.TEXT_SECONDARY))
        painter.setFont(body_font)
        painter.drawText(margin + 12, y + 26, background_name)
        for column, edge in enumerate(BRAND_SIZES):
            painter.drawText(margin + label_width + column * cell, y + 26, f'{edge} px')
        for row, (name, file_name) in enumerate(BRAND_CONCEPTS):
            row_y = y + 40 + row * cell
            painter.setPen(QColor('#202020' if light else styles.TEXT_PRIMARY))
            painter.drawText(margin + 12, row_y + cell // 2, name)
            for column, edge in enumerate(BRAND_SIZES):
                icon = render_svg(BRAND_DIR / file_name, edge)
                x = margin + label_width + column * cell
                painter.drawPixmap(x, row_y + (cell - edge) // 2, icon)
        y += block_height + 16
    wordmark = QSvgRenderer(str(BRAND_DIR / 'wordmark.svg'))
    painter.setPen(QColor(styles.TEXT_SECONDARY))
    painter.setFont(body_font)
    painter.drawText(margin, y + 14, 'Wordmark (rendered with the bundled Space Grotesk):')
    wordmark.render(painter, QRectF(margin + 360, y - 6, 200, 70))
    painter.end()
    return sheet


def build_preview(parent: QWidget | None = None) -> QWidget:
    content = QWidget(parent)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(styles.PAGE_PADDING_H, styles.PAGE_PADDING_V,
                              styles.PAGE_PADDING_H, styles.PAGE_PADDING_V)
    layout.setSpacing(0)
    layout.addWidget(c.page_title('TrophyTracker components'))
    layout.addWidget(c.text_label('R17 component preview · synthetic sample data', 'secondary'))
    buttons, focus_target = _buttons()
    for section in (_typography(), _swatches(), buttons, _chips_and_navigation(), _inputs(),
                    _progress_and_metrics(), _cards_and_rows(), _menus_and_dialogs(content)):
        layout.addWidget(section)
    layout.addStretch(1)
    content._focus_target = focus_target  # type: ignore[attr-defined]
    return content


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--screenshot', type=Path, help='write the component preview to a PNG and exit')
    parser.add_argument('--brand-sheet', type=Path, help='write the brand size comparison to a PNG and exit')
    args = parser.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    styles.apply_theme(app)

    if args.brand_sheet:
        build_brand_sheet().save(str(args.brand_sheet))
        print(f'Wrote {args.brand_sheet}')
        if not args.screenshot:
            return 0

    content = build_preview()
    if args.screenshot:
        content.setFixedWidth(PREVIEW_WIDTH)
        content.adjustSize()
        content.show()
        app.processEvents()
        content._focus_target.setFocus(Qt.FocusReason.TabFocusReason)  # type: ignore[attr-defined]
        app.processEvents()
        content.grab().save(str(args.screenshot))
        print(f'Wrote {args.screenshot}')
        return 0

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    scroll.setWindowTitle('TrophyTracker components')
    scroll.resize(QSize(PREVIEW_WIDTH + 40, 900))
    scroll.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
