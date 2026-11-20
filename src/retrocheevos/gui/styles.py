"""TrophyTracker visual identity: ink surfaces, mint accents and warm highlights."""

BG = '#0b1120'
BOX_BG = '#111b2b'
EMBED = '#0e1726'
EMBED_HIGHLIGHT = '#223149'
HEADING = '#f0f5fc'
TEXT = '#d9e3f1'
TEXT_MUTED = '#63738b'
TEXT_DIM = '#9aabc2'
DANGER = '#ff957f'
DIVIDER = '#293952'
LINK = '#6ce7c4'
LINK_HOVER = '#a5f4dd'
MENU_LINK = TEXT
PROGRESS_HARDCORE = LINK
PROGRESS_SOFTCORE = '#86b8ff'
POINTS_BLUE = LINK
FONT_FAMILY = '"Inter", "Noto Sans", "Segoe UI", sans-serif'
FONT_SIZE_PT = 10
HEADING_SIZE_PT = 18
RADIUS = 10
PADDING_V = 8
PADDING_H = 12
PROGRESS_HEIGHT = 8

SECTION_HEADER_STYLESHEET = f"""
QLabel {{
    color: {TEXT_DIM}; font-size: 10pt; font-weight: 600;
    background: transparent; border: none; padding: 10px 4px;
}}
"""

APP_STYLESHEET = f"""
QWidget {{
    background-color: {BG}; color: {TEXT};
    font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_PT}pt;
}}
QWidget#brandHeader {{ background-color: #101826; border-bottom: 1px solid {EMBED_HIGHLIGHT}; }}
QWidget#navigation {{ background-color: #101826; border-bottom: 1px solid {EMBED_HIGHLIGHT}; }}
QLabel {{ background: transparent; border: none; padding: 0; }}
QLabel#brandName {{ color: {HEADING}; font-size: 22pt; font-weight: 700; }}
QLabel#brandTagline, QLabel#pageSubtitle {{ color: {TEXT_DIM}; font-size: 10pt; }}
QLabel#pageTitle {{ color: {HEADING}; font-size: 22pt; font-weight: 700; padding: 4px 0; }}
QLabel#eyebrow {{ color: {TEXT_DIM}; font-size: 8pt; font-weight: 600; }}
QLabel#versionBadge {{ color: {TEXT_DIM}; background: {BOX_BG}; border-radius: 8px; padding: 5px 10px; }}
QGroupBox {{
    background-color: {BOX_BG}; border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: 12px; margin-top: 14px; padding: 16px 12px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 14px; padding: 0 6px; color: {HEADING}; font-weight: 600;
}}
QGroupBox#nowPlaying {{ border: 1px solid #345c58; background-color: #11252c; }}
QFrame {{ background-color: {BOX_BG}; border: 1px solid {EMBED_HIGHLIGHT}; border-radius: 10px; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ border: none; background: transparent; }}
QLabel {{ background: transparent; border: none; padding: 0; }}
QPushButton {{
    background-color: #19263a; color: {TEXT}; border: 1px solid {DIVIDER};
    border-radius: {RADIUS}px; padding: {PADDING_V}px {PADDING_H}px; font-weight: 500;
}}
QPushButton:hover {{ background-color: #24364b; border-color: {LINK}; color: {HEADING}; }}
QPushButton:pressed {{ background-color: #2b4251; }}
QPushButton:disabled {{ background-color: #131e2e; color: {TEXT_MUTED}; border-color: {EMBED_HIGHLIGHT}; }}
QPushButton[primary="true"] {{ background-color: {LINK}; color: #10251f; border-color: {LINK}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background-color: {LINK_HOVER}; border-color: {LINK_HOVER}; }}
QPushButton#navButton {{ background: transparent; border: 1px solid transparent; color: {TEXT_DIM}; padding: 9px 18px; }}
QPushButton#navButton:hover {{ color: {HEADING}; background: {BOX_BG}; }}
QPushButton#navButton:checked {{ color: {LINK}; background-color: #18332f; border-color: #2e6557; }}
QPushButton#accountButton {{ background: {BOX_BG}; border: 1px solid {DIVIDER}; border-radius: 22px; padding: 4px; }}
QPushButton#accountButton:hover {{ border-color: {LINK}; }}
QLineEdit, QComboBox, QSpinBox, QAbstractSpinBox {{
    background-color: {EMBED}; color: {TEXT}; border: 1px solid {DIVIDER};
    border-radius: {RADIUS}px; padding: 8px 10px; min-height: 18px;
    selection-background-color: #2e6557; selection-color: {HEADING};
}}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{ border-color: {LINK}; background-color: #142235; }}
QLineEdit#globalSearch {{ padding: 12px 16px; border-radius: 12px; font-size: 11pt; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {BOX_BG}; color: {TEXT}; border: 1px solid {DIVIDER};
    selection-background-color: #244e46; selection-color: {HEADING}; outline: none;
}}
QListWidget, QTableView, QTreeView {{
    background-color: {EMBED}; alternate-background-color: #131f31;
    border: 1px solid {EMBED_HIGHLIGHT}; border-radius: 10px; outline: none;
}}
QListWidget::item, QTableView::item {{ padding: 6px 10px; border: none; }}
QListWidget::item:hover, QTableView::item:hover {{ background-color: #1b3044; }}
QListWidget::item:selected, QTableView::item:selected {{ background-color: #24463f; color: {HEADING}; }}
QTableView {{ gridline-color: {EMBED_HIGHLIGHT}; }}
QHeaderView::section {{ background-color: #172337; color: {TEXT_DIM}; border: none; border-bottom: 1px solid {DIVIDER}; padding: 10px; font-weight: 600; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QProgressBar {{ background-color: #0c1926; border: none; border-radius: 6px; min-height: 10px; text-align: center; color: {HEADING}; }}
QProgressBar::chunk {{ background-color: #348c79; border-radius: 6px; }}
QTabWidget::pane {{ background-color: {EMBED}; border: 1px solid {EMBED_HIGHLIGHT}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; padding: 7px 12px; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {LINK}; border-bottom-color: {LINK}; }}
QTabBar::tab:hover {{ color: {HEADING}; }}
QMenu {{ background-color: #142033; color: {TEXT}; border: 1px solid {DIVIDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background-color: #25473f; color: {LINK_HOVER}; }}
QMenu::separator {{ height: 1px; background: {DIVIDER}; margin: 5px; }}
QToolTip {{ background-color: #20314a; color: {HEADING}; border: 1px solid {DIVIDER}; padding: 7px; }}
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {DIVIDER}; border-radius: 4px; background: {EMBED}; }}
QCheckBox::indicator:checked {{ background-color: {LINK}; border-color: {LINK}; }}
QSlider::groove:horizontal {{ height: 4px; background: {DIVIDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: #3f9f8a; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {LINK}; width: 13px; height: 13px; margin: -5px 0; border-radius: 6px; }}
QDialog, QMessageBox {{ background-color: {BG}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 0; }}
QScrollBar::handle:vertical {{ background: #35465f; min-height: 30px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: #58718d; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 2px; }}
QScrollBar::handle:horizontal {{ background: #35465f; min-width: 30px; border-radius: 4px; }}
QScrollBar::handle:horizontal:hover {{ background: #58718d; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; background: none; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
"""
SCROLLBAR_STYLESHEET = APP_STYLESHEET


def apply_theme(app) -> None:
    """Use the same palette for native delegates, dialogs and styled widgets."""
    from PySide6.QtGui import QColor, QPalette
    app.setStyle('Fusion')
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, EMBED), (QPalette.ColorRole.AlternateBase, BOX_BG),
        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, BOX_BG),
        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, '#24463f'),
        (QPalette.ColorRole.HighlightedText, HEADING), (QPalette.ColorRole.ToolTipBase, EMBED),
        (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.Link, LINK),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(TEXT_MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_MUTED))
    app.setPalette(palette)
    app.setStyleSheet(APP_STYLESHEET)
