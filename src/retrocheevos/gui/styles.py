"""App-wide Qt stylesheet, matching RetroAchievements' own visual system.

Applied once, at `QApplication` construction (`main.py`), so it covers every
page, list and table automatically — no per-page styling needed.

**Where these values come from.** They are RA's own design tokens, taken from
the site's source rather than eyeballed from screenshots: the site is open
source (`RetroAchievements/RAWeb`), and `resources/css/theme.css` defines the
whole scheme as CSS custom properties. The site itself sits behind Cloudflare
and returns HTTP 403 to non-browser requests, so scraping the rendered pages
wasn't possible; the repository gives the exact numbers instead, which is a
better source anyway — no colour is inferred from a JPEG.

The constants below map one-to-one onto RA's variables, named the same way so
the correspondence stays checkable:

    RA `--bg-color`              -> BG
    RA `--box-bg-color`          -> BOX_BG
    RA `--embed-color`           -> EMBED
    RA `--embed-highlight-color` -> EMBED_HIGHLIGHT
    RA `--heading-color`         -> HEADING
    RA `--link-color`            -> LINK      (the default gold theme)
    RA `--link-hover-color`      -> LINK_HOVER
    RA `--text-color`            -> TEXT
    RA `--text-color-muted`      -> TEXT_MUTED
    RA `--divider-color`         -> DIVIDER

RA ships several schemes (dark/black/light) and accent themes; this takes the
**default dark scheme with the default gold accent**, which is what an
unconfigured account sees.

Two deliberate departures, both because Qt is not a browser:

- `TEXT_MUTED` is RA's `rgb(75,75,75)`, which is nearly invisible on Qt's
  flat panels — the site uses it against larger type with more contrast
  around it. `TEXT_DIM` is provided for secondary label text instead, and
  `TEXT_MUTED` is kept for genuinely disabled things.
- Font size: RA uses CSS `small`, which resolves against the browser's root
  size. `FONT_SIZE_PT` is the point-size equivalent, since Qt has no such
  relative keyword.
"""

# --- RA scheme: dark (default) ---------------------------------------
BG = "#1a1a1a"  # rgb(26, 26, 26)
BOX_BG = "#232323"  # rgb(35, 35, 35)
EMBED = "#161616"  # rgb(22, 22, 22)
EMBED_HIGHLIGHT = "#2a2a2a"  # rgb(42, 42, 42)
HEADING = "#d2d2d2"  # rgb(210, 210, 210)
TEXT = "#c8c8c8"  # rgb(200, 200, 200)
TEXT_MUTED = "#4b4b4b"  # rgb(75, 75, 75) — disabled only, see module docstring
TEXT_DIM = "#8a8a8a"  # Qt-only: secondary text that still has to be readable
DANGER = "#ff0000"  # rgb(255, 0, 0)
DIVIDER = "#5a5a5a"  # rgb(90, 90, 90)

# --- RA accent: default "gold" theme ----------------------------------
LINK = "#cc9900"  # rgb(204, 153, 0)
LINK_HOVER = "#eeeeee"  # rgb(238, 238, 238)
MENU_LINK = "#c8c8c8"  # rgb(200, 200, 200)

# Progress fills, straight from `resources/css/progress.css`. RA distinguishes
# the two and so does this app: hardcore is the gold accent, softcore blue.
PROGRESS_HARDCORE = "#cc9900"  # rgb(204, 153, 0)
PROGRESS_SOFTCORE = "#0b71c1"  # rgb(11, 113, 193)

# Points. Deliberately *not* the gold accent: gold marks things you can act
# on (buttons, links), and using it for a read-only number made every screen
# read as if it were covered in controls. RA's own non-gold theme uses
# `--color-blue-400` for its accent, which is this.
POINTS_BLUE = "#4a90e2"

# --- Typography (resources/css/typography.css) ------------------------
FONT_FAMILY = "Verdana, Arial, sans-serif"
FONT_SIZE_PT = 9  # CSS `small`
HEADING_SIZE_PT = 14

# --- Metrics ----------------------------------------------------------
# RA's `.btn`: 4px radius, 0.4em/0.6em padding. Table cells: 4px 8px, headers
# 8px. Progress bars: 6px tall.
RADIUS = 4
PADDING_V = 5
PADDING_H = 8
PROGRESS_HEIGHT = 6

# A heading that looks like a button but isn't one — same box, border and
# gold text as `.btn`, centred, no hover and no pointer cursor. Used for the
# sidebar section headings so they sit visually level with the real button
# above them. Deliberately a QLabel, not a disabled QPushButton: a disabled
# button greys out and reads as "you can't do this yet" rather than "this is
# a title". Defined here, after the metrics it interpolates.
SECTION_HEADER_STYLESHEET = f"""
QLabel {{
    background-color: {EMBED};
    color: {LINK};
    border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: {RADIUS}px;
    padding: {PADDING_V}px {PADDING_H}px;
}}
"""

APP_STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_PT}pt;
}}

/* RA's headings are normal weight with a rule under them
   (`main h1, h2, h3 {{ border-bottom: 1px solid var(--heading-color) }}`). */
QGroupBox {{
    background-color: {BOX_BG};
    border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: {RADIUS}px;
    margin-top: 12px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: {HEADING};
}}

QFrame {{
    background-color: {BOX_BG};
    border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: {RADIUS}px;
}}
/* Layout-only frames (separators, containers) must not pick up the panel
   look — QSS has no "only if it has no children" selector, so the frame
   shapes that are purely structural are excluded by shape instead. */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    border: none;
    background: transparent;
}}

/* MUST come after the QFrame rule above. In Qt, QLabel *inherits from
   QFrame*, so that rule gives every label its own bordered box — and with
   equal specificity, QSS resolves the conflict by source order, last one
   wins. Placed before QFrame this whole block is silently ignored, which is
   exactly what happened the first time: the UI rendered as a grid of empty
   rectangles around the text. Same story for QLineEdit/QListWidget/
   QScrollArea, all QFrame subclasses, all styled further down. */
QLabel {{
    background: transparent;
    border: none;
    padding: 0;
}}

QPushButton {{
    background-color: {EMBED};
    color: {LINK};
    border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: {RADIUS}px;
    padding: {PADDING_V}px {PADDING_H}px;
}}
QPushButton:hover {{
    background-color: {EMBED_HIGHLIGHT};
    color: {LINK_HOVER};
    border: 1px solid {MENU_LINK};
}}
QPushButton:pressed {{
    background-color: {BG};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border: 1px solid {EMBED};
}}

QLineEdit, QComboBox, QSpinBox, QAbstractSpinBox {{
    background-color: {EMBED};
    color: {TEXT};
    border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: {RADIUS}px;
    padding: {PADDING_V}px {PADDING_H}px;
    selection-background-color: {LINK};
    selection-color: {EMBED};
}}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{
    border: 1px solid {LINK};
}}
QComboBox QAbstractItemView {{
    background-color: {EMBED};
    color: {TEXT};
    border: 1px solid {EMBED_HIGHLIGHT};
    selection-background-color: {EMBED_HIGHLIGHT};
    selection-color: {LINK_HOVER};
}}

QListWidget, QTableView, QTreeView, QScrollArea {{
    background-color: {EMBED};
    border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: {RADIUS}px;
}}
/* RA stripes odd rows `rgba(50,50,50,.3)` and hovers `rgba(128,128,128,.2)`. */
QTableView {{
    alternate-background-color: rgba(50, 50, 50, 77);
    gridline-color: {EMBED_HIGHLIGHT};
}}
QListWidget::item, QTableView::item {{
    padding: 4px 8px;
}}
QListWidget::item:hover, QTableView::item:hover {{
    background-color: rgba(128, 128, 128, 51);
}}
QListWidget::item:selected, QTableView::item:selected {{
    background-color: {EMBED_HIGHLIGHT};
    color: {LINK_HOVER};
}}
QHeaderView::section {{
    background-color: {BOX_BG};
    color: {MENU_LINK};
    border: none;
    border-bottom: 1px solid {EMBED_HIGHLIGHT};
    padding: 8px;
    text-align: left;
}}

QProgressBar {{
    background-color: {EMBED};
    border: 1px solid {EMBED_HIGHLIGHT};
    border-radius: {RADIUS}px;
    text-align: center;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background-color: {PROGRESS_HARDCORE};
    border-radius: {RADIUS - 1}px;
}}

QMenu {{
    background-color: {EMBED};
    color: {TEXT};
    border: 1px solid {EMBED_HIGHLIGHT};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 16px;
}}
QMenu::item:selected {{
    background-color: {EMBED_HIGHLIGHT};
    color: {LINK_HOVER};
}}
QMenu::separator {{
    height: 1px;
    background: {EMBED_HIGHLIGHT};
    margin: 4px 2px;
}}

QToolTip {{
    background-color: {EMBED};
    color: {TEXT};
    border: 1px solid {DIVIDER};
    padding: 4px;
}}

QCheckBox {{
    background: transparent;
    spacing: 6px;
}}

QMessageBox, QDialog {{
    background-color: {BG};
}}

/* Overrides Windows' native thin, hover-to-expand scrollbar with a
   consistently wide, always-clickable one. QSS-drawn scrollbars replace the
   native OS rendering entirely, so this also removes the hover-expand
   animation itself, not just its width. */
QScrollBar:vertical {{
    background: transparent;
    width: 14px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: rgba(120, 120, 120, 160);
    min-height: 30px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(120, 120, 120, 220);
}}
QScrollBar::handle:vertical:pressed {{
    background: rgba(90, 90, 90, 220);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 14px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: rgba(120, 120, 120, 160);
    min-width: 30px;
    border-radius: 6px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(120, 120, 120, 220);
}}
QScrollBar::handle:horizontal:pressed {{
    background: rgba(90, 90, 90, 220);
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}
"""

# Kept so `main.py`'s existing import keeps working; the scrollbar rules are
# part of `APP_STYLESHEET` now.
SCROLLBAR_STYLESHEET = APP_STYLESHEET
