"""TrophyTracker visual system: semantic design tokens and the application stylesheet.

Tokens follow the reviewed UI proposal (roadmap R17): dark purple surfaces,
gold for achievements, progress and primary actions, turquoise for secondary
highlights. Widgets should use the semantic names below (or the components in
`gui/components.py`) instead of hex values.

The names at the end of the color section (`BG`, `BOX_BG`, `LINK`, ...) are
aliases kept for widgets written before the revamp. They map onto the new
tokens and are removed as each screen is converted (R27).
"""

# --- Color tokens -----------------------------------------------------------

# Surfaces, from the reference palette.
SURFACE_APP = '#14121C'          # application background
SURFACE_SIDEBAR = '#0F0D16'      # sidebar background
SURFACE_PANEL = '#1E1B2B'        # panels and cards
SURFACE_RAISED = '#2A2540'       # selected navigation, secondary controls
SURFACE_HOVER = '#332D4D'        # hover on raised controls (derived)
SURFACE_INPUT = '#181524'        # text fields and lists (derived)
PROGRESS_TRACK = '#2E2A44'
OUTLINE_MUTED = '#3A3555'        # decorative dividers and muted badges

# Control boundaries need 3:1 against neighbouring surfaces (R26). The
# reference outline (#3A3555) reaches only 1.5:1 on panels, so interactive
# control borders use this derived token instead.
OUTLINE_CONTROL = '#726A99'

# Text.
TEXT_PRIMARY = '#ECE9F5'
TEXT_SECONDARY = '#A9A4BD'
TEXT_DISABLED = '#6E6886'        # disabled controls only; exempt from contrast rules
TEXT_ON_ACCENT = '#1A1408'       # text on gold

# Accents.
ACCENT_GOLD = '#F5B83D'          # achievements, progress, primary actions
ACCENT_GOLD_HOVER = '#F8C963'
ACCENT_GOLD_PRESSED = '#D99E28'
ACCENT_GOLD_SOFT = '#3A2F1C'     # selected chip background
ACCENT_TURQUOISE = '#3DD6C3'     # secondary highlights, focus, links
ACCENT_TURQUOISE_HOVER = '#7BE5D8'
FOCUS_RING = ACCENT_TURQUOISE

# Status.
STATUS_DANGER = '#FF8A8A'
STATUS_DANGER_SOFT = '#3A1E27'
STATUS_SUCCESS = ACCENT_TURQUOISE

# Progress by mode. Hardcore and softcore are never merged; their bars also
# carry a text label so color is not the only signal.
PROGRESS_HARDCORE = ACCENT_GOLD
PROGRESS_SOFTCORE = ACCENT_TURQUOISE

# Every token, for the component preview and the contrast tests.
COLOR_TOKENS = {
    name: value for name, value in globals().items()
    if name.isupper() and isinstance(value, str) and value.startswith('#')
}

# Legacy aliases (pre-revamp widgets).
BG = SURFACE_APP
BOX_BG = SURFACE_PANEL
EMBED = SURFACE_INPUT
EMBED_HIGHLIGHT = OUTLINE_MUTED
HEADING = TEXT_PRIMARY
TEXT = TEXT_PRIMARY
TEXT_MUTED = TEXT_DISABLED
TEXT_DIM = TEXT_SECONDARY
DANGER = STATUS_DANGER
DIVIDER = OUTLINE_MUTED
LINK = ACCENT_TURQUOISE
LINK_HOVER = ACCENT_TURQUOISE_HOVER
MENU_LINK = TEXT_PRIMARY
POINTS_BLUE = ACCENT_GOLD

# --- Typography -------------------------------------------------------------

FONT_UI = 'Inter'
FONT_DISPLAY = 'Space Grotesk'
FONT_FAMILY = f'"{FONT_UI}", "Noto Sans", "Segoe UI", sans-serif'
FONT_FAMILY_DISPLAY = f'"{FONT_DISPLAY}", "{FONT_UI}", "Noto Sans", "Segoe UI", sans-serif'

# Reference sizes in pixels (scaled by Qt's device pixel ratio).
TYPE_PAGE_TITLE_PX = 28
TYPE_SECTION_PX = 16
TYPE_METRIC_PX = 32
TYPE_BODY_PX = 14
TYPE_SECONDARY_PX = 13
TYPE_CAPTION_PX = 12
TYPE_SIDEBAR_BRAND_PX = 20

# Legacy point sizes, still read by a few widgets.
FONT_SIZE_PT = 10
HEADING_SIZE_PT = 18

# --- Shape, size and spacing ------------------------------------------------

RADIUS_PANEL = 12
RADIUS_CONTROL = 8
RADIUS_COVER = 8
RADIUS_PILL = 18

HEIGHT_BUTTON = 44
HEIGHT_BUTTON_COMPACT = 40
HEIGHT_CHIP = 36
HEIGHT_PROGRESS = 8

SIDEBAR_WIDTH = 220
PAGE_PADDING_V = 28
PAGE_PADDING_H = 32
GAP = 16
SPACE_XS = 4
SPACE_S = 8
SPACE_M = 12
SPACE_L = 24

# Legacy names.
RADIUS = RADIUS_CONTROL
PADDING_V = 8
PADDING_H = 12
PROGRESS_HEIGHT = HEIGHT_PROGRESS

SECTION_HEADER_STYLESHEET = f"""
QLabel {{
    color: {TEXT_SECONDARY}; font-size: {TYPE_SECONDARY_PX}px; font-weight: 600;
    background: transparent; border: none; padding: 10px 4px;
}}
"""

# Borders are always 2 px (transparent when idle) so focus and selection
# never shift the layout.
APP_STYLESHEET = f"""
QWidget {{
    background-color: {SURFACE_APP}; color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY}; font-size: {TYPE_BODY_PX}px;
}}
QLabel {{ background: transparent; border: none; padding: 0; }}

/* Typography roles */
QLabel[role="pageTitle"], QLabel#pageTitle {{
    font-family: {FONT_FAMILY_DISPLAY}; font-size: {TYPE_PAGE_TITLE_PX}px; font-weight: 700;
    color: {TEXT_PRIMARY}; padding: 4px 0;
}}
QLabel[role="sectionTitle"] {{
    font-family: {FONT_FAMILY_DISPLAY}; font-size: {TYPE_SECTION_PX}px; font-weight: 700;
    color: {TEXT_PRIMARY};
}}
QLabel[role="metric"] {{
    font-family: {FONT_FAMILY_DISPLAY}; font-size: {TYPE_METRIC_PX}px; font-weight: 700;
    color: {TEXT_PRIMARY};
}}
QLabel[role="secondary"], QLabel#pageSubtitle {{
    color: {TEXT_SECONDARY}; font-size: {TYPE_SECONDARY_PX}px;
}}
QLabel[role="caption"], QLabel#eyebrow {{
    color: {TEXT_SECONDARY}; font-size: {TYPE_CAPTION_PX}px; font-weight: 600;
}}
QLabel[role="points"] {{ color: {ACCENT_GOLD}; font-weight: 600; }}
QLabel[role="error"] {{ color: {STATUS_DANGER}; }}
QLabel#sidebarBrand {{
    font-family: {FONT_FAMILY_DISPLAY}; color: {TEXT_PRIMARY};
    font-size: {TYPE_SIDEBAR_BRAND_PX}px; font-weight: 700;
}}
QLabel#versionBadge {{
    color: {TEXT_SECONDARY}; background: {SURFACE_PANEL};
    border-radius: {RADIUS_CONTROL}px; padding: 5px 10px; font-size: {TYPE_CAPTION_PX}px;
}}

/* Status pills: always carry text, never color alone */
QLabel[pill] {{
    border-radius: 10px; padding: 2px 10px; font-size: {TYPE_CAPTION_PX}px; font-weight: 600;
    background: {SURFACE_RAISED}; color: {TEXT_SECONDARY};
}}
QLabel[pill="hardcore"] {{ background: {ACCENT_GOLD}; color: {TEXT_ON_ACCENT}; }}
QLabel[pill="softcore"] {{ background: {SURFACE_RAISED}; color: {ACCENT_TURQUOISE}; }}
QLabel[pill="mastered"] {{ background: {ACCENT_GOLD_SOFT}; color: {ACCENT_GOLD}; }}
QLabel[pill="error"] {{ background: {STATUS_DANGER_SOFT}; color: {STATUS_DANGER}; }}

/* Shell */
QWidget#sidebar {{ background-color: {SURFACE_SIDEBAR}; }}
QFrame#sidebar {{ border: none; border-right: 1px solid {OUTLINE_MUTED}; border-radius: 0; }}
QFrame#sidebar QLabel {{ background: transparent; }}

/* Surfaces */
QGroupBox {{
    background-color: {SURFACE_PANEL}; border: 1px solid {OUTLINE_MUTED};
    border-radius: {RADIUS_PANEL}px; margin-top: 14px; padding: 16px 12px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 14px; padding: 0 6px; color: {TEXT_PRIMARY}; font-weight: 600;
}}
QGroupBox#nowPlaying {{ border: 1px solid {ACCENT_TURQUOISE}; }}
QFrame {{
    background-color: {SURFACE_PANEL}; border: 1px solid {OUTLINE_MUTED};
    border-radius: {RADIUS_PANEL}px;
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ border: none; background: transparent; }}
QFrame[surface="panel"] {{ background-color: {SURFACE_PANEL}; border: none; }}
QFrame[surface="card"] {{ background-color: {SURFACE_PANEL}; border: 2px solid transparent; }}
QFrame[surface="card"]:hover {{ border-color: {OUTLINE_MUTED}; }}
QFrame[surface="row"] {{
    background-color: transparent; border: none; border-bottom: 1px solid {OUTLINE_MUTED};
    border-radius: 0;
}}
QFrame[surface="cover"] {{
    background-color: {SURFACE_RAISED}; border: none; border-radius: {RADIUS_COVER}px;
}}
/* QLabel inherits QFrame: reset it after the QFrame rules so plain labels stay
   transparent. Role and pill selectors above are more specific and still apply. */
QLabel {{ background: transparent; border: none; padding: 0; }}

/* Buttons: secondary is the default; primary is gold */
QPushButton {{
    background-color: {SURFACE_RAISED}; color: {TEXT_PRIMARY};
    border: 2px solid transparent; border-radius: {RADIUS_CONTROL}px;
    padding: 0 16px; min-height: {HEIGHT_BUTTON - 4}px; font-weight: 500;
}}
QPushButton:hover {{ background-color: {SURFACE_HOVER}; }}
QPushButton:pressed {{ background-color: {OUTLINE_MUTED}; }}
QPushButton:focus {{ border-color: {FOCUS_RING}; }}
QPushButton:disabled {{ background-color: {SURFACE_PANEL}; color: {TEXT_DISABLED}; }}
QPushButton[variant="primary"], QPushButton[primary="true"] {{
    background-color: {ACCENT_GOLD}; color: {TEXT_ON_ACCENT}; font-weight: 600;
}}
QPushButton[variant="primary"]:hover, QPushButton[primary="true"]:hover {{ background-color: {ACCENT_GOLD_HOVER}; }}
QPushButton[variant="primary"]:pressed, QPushButton[primary="true"]:pressed {{ background-color: {ACCENT_GOLD_PRESSED}; }}
QPushButton[variant="primary"]:focus, QPushButton[primary="true"]:focus {{ border-color: {TEXT_PRIMARY}; }}
QPushButton[variant="primary"]:disabled, QPushButton[primary="true"]:disabled {{
    background-color: {SURFACE_PANEL}; color: {TEXT_DISABLED};
}}
QPushButton[variant="ghost"] {{ background-color: transparent; color: {ACCENT_TURQUOISE}; }}
QPushButton[variant="ghost"]:hover {{ background-color: {SURFACE_RAISED}; color: {ACCENT_TURQUOISE_HOVER}; }}
QPushButton[variant="ghost"]:disabled {{ background-color: transparent; color: {TEXT_DISABLED}; }}
QPushButton[variant="danger"] {{ background-color: {STATUS_DANGER_SOFT}; color: {STATUS_DANGER}; }}
QPushButton[variant="danger"]:hover {{ background-color: #4A2531; }}
QPushButton[variant="danger"]:disabled {{ background-color: {SURFACE_PANEL}; color: {TEXT_DISABLED}; }}
QPushButton[size="compact"] {{ min-height: {HEIGHT_BUTTON_COMPACT - 4}px; padding: 0 14px; }}

/* Filter chips */
QPushButton[chip="true"] {{
    background-color: transparent; color: {TEXT_SECONDARY};
    border: 2px solid {OUTLINE_CONTROL}; border-radius: {RADIUS_PILL}px;
    min-height: {HEIGHT_CHIP - 4}px; padding: 0 14px;
}}
QPushButton[chip="true"]:hover {{ color: {TEXT_PRIMARY}; background-color: {SURFACE_RAISED}; }}
QPushButton[chip="true"]:checked {{
    background-color: {ACCENT_GOLD_SOFT}; color: {ACCENT_GOLD}; border-color: {ACCENT_GOLD};
}}
QPushButton[chip="true"]:focus {{ border-color: {FOCUS_RING}; }}
QPushButton[chip="true"]:disabled {{ color: {TEXT_DISABLED}; border-color: {OUTLINE_MUTED}; }}

/* Navigation */
QPushButton#sidebarItem {{
    background: transparent; color: {TEXT_SECONDARY}; text-align: left;
    border: 2px solid transparent; border-radius: {RADIUS_CONTROL}px;
    padding: 0 14px; min-height: {HEIGHT_BUTTON_COMPACT - 4}px;
}}
QPushButton#sidebarItem:hover {{
    color: {TEXT_PRIMARY}; background: {SURFACE_PANEL};
}}
QPushButton#sidebarItem:checked {{
    color: {TEXT_PRIMARY}; background-color: {SURFACE_RAISED}; font-weight: 600;
    border-left: 2px solid {ACCENT_GOLD};
}}
QPushButton#sidebarItem:focus {{ border-color: {FOCUS_RING}; }}
QPushButton#sidebarItem:disabled {{ color: {TEXT_DISABLED}; }}
QPushButton#accountPanel {{
    background: transparent; border: 2px solid transparent;
    border-radius: {RADIUS_CONTROL}px; padding: 0; text-align: left;
}}
QPushButton#accountPanel:hover {{ background: {SURFACE_PANEL}; }}
QPushButton#accountPanel:pressed {{ background: {SURFACE_RAISED}; }}
QPushButton#accountPanel:focus {{ border-color: {FOCUS_RING}; }}
QLabel#accountName {{ color: {TEXT_PRIMARY}; font-weight: 600; }}

/* Inputs */
QLineEdit, QComboBox, QSpinBox, QAbstractSpinBox {{
    background-color: {SURFACE_INPUT}; color: {TEXT_PRIMARY};
    border: 2px solid {OUTLINE_CONTROL}; border-radius: {RADIUS_CONTROL}px;
    padding: 6px 10px; min-height: 22px;
    selection-background-color: {SURFACE_HOVER}; selection-color: {TEXT_PRIMARY};
}}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{ border-color: {FOCUS_RING}; }}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{
    color: {TEXT_DISABLED}; border-color: {OUTLINE_MUTED};
}}
QLineEdit[invalid="true"] {{ border-color: {STATUS_DANGER}; }}
QLineEdit[search="true"], QLineEdit#globalSearch {{
    padding: 8px 14px; border-radius: {RADIUS_PILL}px; min-height: {HEIGHT_BUTTON - 20}px;
}}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_PANEL}; color: {TEXT_PRIMARY}; border: 1px solid {OUTLINE_MUTED};
    selection-background-color: {SURFACE_RAISED}; selection-color: {TEXT_PRIMARY}; outline: none;
}}

/* Item views */
QListWidget, QTableView, QTreeView {{
    background-color: {SURFACE_INPUT}; alternate-background-color: {SURFACE_PANEL};
    border: 1px solid {OUTLINE_MUTED}; border-radius: {RADIUS_PANEL}px; outline: none;
}}
QListWidget:focus, QTableView:focus, QTreeView:focus {{ border-color: {FOCUS_RING}; }}
QListWidget::item, QTableView::item {{ padding: 6px 10px; border: none; }}
QListWidget::item:hover, QTableView::item:hover {{ background-color: {SURFACE_PANEL}; }}
QListWidget::item:selected, QTableView::item:selected {{
    background-color: {SURFACE_RAISED}; color: {TEXT_PRIMARY};
}}
QTableView {{ gridline-color: {OUTLINE_MUTED}; }}
QHeaderView::section {{
    background-color: {SURFACE_PANEL}; color: {TEXT_SECONDARY}; border: none;
    border-bottom: 1px solid {OUTLINE_MUTED}; padding: 10px; font-weight: 600;
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
/* The main page stack is a QFrame; keep it on the app background so panels
   and metric cards stand out as in the reviewed boards (R19). */
QStackedWidget#pages {{ background-color: {SURFACE_APP}; border: none; border-radius: 0; }}
/* Layout-only containers inside scrolled pages */
QWidget[transparent="true"] {{ background: transparent; }}

/* Progress */
QProgressBar {{
    background-color: {PROGRESS_TRACK}; border: none; border-radius: 4px;
    min-height: {HEIGHT_PROGRESS}px; max-height: {HEIGHT_PROGRESS}px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background-color: {PROGRESS_HARDCORE}; border-radius: 4px; }}
QProgressBar[mode="softcore"]::chunk {{ background-color: {PROGRESS_SOFTCORE}; }}

/* Tabs, menus, tooltips */
QTabWidget::pane {{
    background-color: {SURFACE_INPUT}; border: 1px solid {OUTLINE_MUTED};
    border-radius: {RADIUS_CONTROL}px; top: -1px;
}}
QTabBar::tab {{
    background: transparent; color: {TEXT_SECONDARY}; padding: 7px 12px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT_PRIMARY}; border-bottom-color: {ACCENT_GOLD}; }}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}
QMenu {{
    background-color: {SURFACE_PANEL}; color: {TEXT_PRIMARY}; border: 1px solid {OUTLINE_MUTED};
    border-radius: {RADIUS_CONTROL}px; padding: 6px;
}}
QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background-color: {SURFACE_RAISED}; color: {TEXT_PRIMARY}; }}
QMenu::item:disabled {{ color: {TEXT_DISABLED}; }}
QMenu::separator {{ height: 1px; background: {OUTLINE_MUTED}; margin: 5px; }}
QToolTip {{
    background-color: {SURFACE_RAISED}; color: {TEXT_PRIMARY};
    border: 1px solid {OUTLINE_CONTROL}; padding: 7px;
}}

/* Checkable controls */
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 2px solid {OUTLINE_CONTROL};
    border-radius: 4px; background: {SURFACE_INPUT};
}}
QCheckBox::indicator:checked {{ background-color: {ACCENT_GOLD}; border-color: {ACCENT_GOLD}; }}
QCheckBox::indicator:focus {{ border-color: {FOCUS_RING}; }}
QCheckBox:disabled {{ color: {TEXT_DISABLED}; }}
QSlider::groove:horizontal {{ height: 4px; background: {PROGRESS_TRACK}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT_GOLD}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT_GOLD}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}

/* Dialogs */
QDialog, QMessageBox {{ background-color: {SURFACE_APP}; }}

/* Scroll bars */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 0; }}
QScrollBar::handle:vertical {{ background: {OUTLINE_MUTED}; min-height: 30px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {OUTLINE_CONTROL}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 2px; }}
QScrollBar::handle:horizontal {{ background: {OUTLINE_MUTED}; min-width: 30px; border-radius: 4px; }}
QScrollBar::handle:horizontal:hover {{ background: {OUTLINE_CONTROL}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; background: none; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
"""
SCROLLBAR_STYLESHEET = APP_STYLESHEET


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio between two `#RRGGBB` colors."""
    def luminance(color: str) -> float:
        channels = [int(color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def apply_theme(app) -> None:
    """Load bundled fonts and apply the palette and stylesheet to the application."""
    from PySide6.QtGui import QColor, QFont, QPalette

    from retrocheevos.gui.assets import load_bundled_fonts

    families = load_bundled_fonts()
    app.setStyle('Fusion')
    if FONT_UI in families:
        font = QFont(FONT_UI)
        font.setPixelSize(TYPE_BODY_PX)
        app.setFont(font)
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, SURFACE_APP), (QPalette.ColorRole.WindowText, TEXT_PRIMARY),
        (QPalette.ColorRole.Base, SURFACE_INPUT), (QPalette.ColorRole.AlternateBase, SURFACE_PANEL),
        (QPalette.ColorRole.Text, TEXT_PRIMARY), (QPalette.ColorRole.Button, SURFACE_RAISED),
        (QPalette.ColorRole.ButtonText, TEXT_PRIMARY), (QPalette.ColorRole.Highlight, SURFACE_RAISED),
        (QPalette.ColorRole.HighlightedText, TEXT_PRIMARY), (QPalette.ColorRole.ToolTipBase, SURFACE_RAISED),
        (QPalette.ColorRole.ToolTipText, TEXT_PRIMARY), (QPalette.ColorRole.Link, ACCENT_TURQUOISE),
        (QPalette.ColorRole.PlaceholderText, TEXT_SECONDARY),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(TEXT_DISABLED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_DISABLED))
    app.setPalette(palette)
    app.setStyleSheet(APP_STYLESHEET)
