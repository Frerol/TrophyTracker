"""App-wide Qt stylesheet (UI.md — visual consistency across pages).

Applied once, at `QApplication` construction (`main.py`), so it covers
every scroll area/list/table in the app automatically — no per-page
styling needed.
"""

# Overrides Windows' native thin, hover-to-expand scrollbar with a
# consistently wide, always-clickable one, styled the same everywhere.
# QSS-drawn scrollbars replace the native OS rendering entirely, so this
# also removes the hover-expand animation itself, not just its width.
SCROLLBAR_STYLESHEET = """
QScrollBar:vertical {
    background: transparent;
    width: 14px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: rgba(120, 120, 120, 160);
    min-height: 30px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(120, 120, 120, 220);
}
QScrollBar::handle:vertical:pressed {
    background: rgba(90, 90, 90, 220);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    background: transparent;
    height: 14px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: rgba(120, 120, 120, 160);
    min-width: 30px;
    border-radius: 6px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(120, 120, 120, 220);
}
QScrollBar::handle:horizontal:pressed {
    background: rgba(90, 90, 90, 220);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
"""
