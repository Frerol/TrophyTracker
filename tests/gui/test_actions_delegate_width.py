"""The Actions column must be wide enough for a row with both buttons, even
when no such row was sampled while sizing it.

This has regressed twice. A column has one width shared by every row, but
this delegate paints "Play" + "+" on installed games and only "+" on the
rest — so a `sizeHint` that answers for its own row makes the column width
depend on which rows Qt happened to measure. `ResizeToContents` samples a
bounded number of them (`resizeContentsPrecision`, 1000 by default) out of a
~12k-row catalog; sample only uninstalled rows and every installed row below
gets its "+" painted past the column edge.

Data-dependent, which is why it comes back: a small or differently-ordered
catalog hides it completely.
"""

import unittest

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTableWidget

from retrocheevos.gui.delegates.explorer_delegates import (
    _BUTTON_MARGIN,
    ActionsDelegate,
)
from retrocheevos.gui.models.explorer_table_model import INSTALLED_ROLE

_app = QApplication.instance() or QApplication([])


class ActionsColumnWidthTests(unittest.TestCase):
    def setUp(self):
        self.table = QTableWidget(2, 1)
        self.delegate = ActionsDelegate()
        self.option = QStyleOptionViewItem()
        self.option.initFrom(self.table)
        self.option.widget = self.table
        self.option.fontMetrics = self.table.fontMetrics()

    def _index(self, *, installed: bool):
        item = self.table.item(0, 0)
        if item is None:
            from PySide6.QtWidgets import QTableWidgetItem

            item = QTableWidgetItem()
            self.table.setItem(0, 0, item)
        item.setData(INSTALLED_ROLE, installed)
        return self.table.model().index(0, 0)

    def test_hint_does_not_depend_on_the_row(self):
        """The whole bug in one assertion."""
        self.option.rect = QRect(0, 0, 200, 32)
        uninstalled = self.delegate.sizeHint(self.option, self._index(installed=False))
        installed = self.delegate.sizeHint(self.option, self._index(installed=True))
        self.assertEqual(uninstalled.width(), installed.width())

    def test_buttons_fit_in_the_hinted_width(self):
        """Size the cell to what `sizeHint` asks for, then check the buttons
        actually land inside it — the original failure was a 9px overflow."""
        for installed in (True, False):
            with self.subTest(installed=installed):
                index = self._index(installed=installed)
                self.option.rect = QRect(0, 0, 200, 32)
                width = self.delegate.sizeHint(self.option, index).width()

                self.option.rect = QRect(0, 0, width, 32)
                rects = self.delegate._button_rects(self.option, index)
                rightmost = max(rect.right() for _key, _label, rect in rects)
                self.assertLessEqual(rightmost, width)

    def test_no_play_button_anywhere(self):
        """Launching lives on the Library page. Explorer offers only "+", on
        installed rows as much as on the rest."""
        for installed in (True, False):
            with self.subTest(installed=installed):
                keys = [
                    key for key, _label in
                    self.delegate._button_specs_for(self._index(installed=installed))
                ]
                self.assertEqual(keys, ["menu"])

    def test_widest_specs_matches_the_real_two_button_row(self):
        """`_widest_specs` is a hardcoded mirror of `_button_specs_for`. If
        someone adds a third button to installed rows and forgets this, the
        column silently goes back to being too narrow."""
        self.assertEqual(
            self.delegate._widest_specs(),
            self.delegate._button_specs_for(self._index(installed=True)),
        )


if __name__ == "__main__":
    unittest.main()
