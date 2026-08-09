"""Reading "the selected row" from a QListWidget, correctly.

Qt keeps *selected* and *current* separate. Clicking a row usually sets
both, but not always — rebuilding a list, restoring it after a refresh, or
selecting programmatically can leave a row highlighted with no current item.
Handlers that read only `currentItem()` then do nothing at all, silently.

That is not hypothetical: "Remove Selected" in Settings did exactly this and
was reported as a dead button. The same pattern was in five other handlers,
two of them also named "Selected".
"""

from typing import Optional

from PySide6.QtWidgets import QListWidget, QListWidgetItem


def selected_item(list_widget: QListWidget) -> Optional[QListWidgetItem]:
    """The row the user means: what is highlighted, falling back to current.

    `selectedItems()` first because that is what "selected" means to the
    person looking at the screen; `currentItem()` after it for keyboard
    navigation, which moves the current row without necessarily selecting it.
    """
    selected = list_widget.selectedItems()
    if selected:
        return selected[0]
    return list_widget.currentItem()
