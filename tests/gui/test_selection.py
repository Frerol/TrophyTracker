"""A highlighted row must count as selected.

`selectedItems()` and `currentItem()` are different things in Qt, and six
handlers read only the second one. With a row visibly highlighted but no
current item they returned silently — reported as "Remove Selected does
nothing when I click it with the account selected".
"""

import unittest

from PySide6.QtWidgets import QApplication, QListWidget

from retrocheevos.gui.selection import selected_item

_app = QApplication.instance() or QApplication([])


class SelectedItemTests(unittest.TestCase):
    def setUp(self):
        self.widget = QListWidget()
        for label in ("first", "second"):
            self.widget.addItem(label)

    def test_empty_list(self):
        self.assertIsNone(selected_item(QListWidget()))

    def test_nothing_selected(self):
        self.widget.clearSelection()
        self.widget.setCurrentItem(None)
        self.assertIsNone(selected_item(self.widget))

    def test_selected_but_not_current(self):
        """The exact reported failure."""
        self.widget.setCurrentItem(None)
        self.widget.item(1).setSelected(True)
        self.assertIsNone(self.widget.currentItem())
        self.assertEqual(selected_item(self.widget).text(), "second")

    def test_current_but_not_selected(self):
        """Keyboard navigation moves current without always selecting."""
        self.widget.setCurrentRow(0)
        self.widget.clearSelection()
        self.assertEqual(selected_item(self.widget).text(), "first")

    def test_selection_wins_over_current(self):
        self.widget.setCurrentRow(0)
        self.widget.clearSelection()
        self.widget.item(1).setSelected(True)
        self.assertEqual(selected_item(self.widget).text(), "second")


if __name__ == "__main__":
    unittest.main()
