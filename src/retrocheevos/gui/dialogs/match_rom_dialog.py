"""Manual ROM-to-game matching dialog (UI.md 3.3) — used when hashing found
no game for an installed ROM, or found the wrong one.

Plain data in via the constructor, result out via a public method, only
queried by the caller after `dialog.exec() == QDialog.DialogCode.Accepted`.
(This used to share that shape with `WatchFolderScanDialog`, deleted in
Bloco 11 — it is now the only dialog in this flow.)

Pre-selects a best-guess match (`difflib.get_close_matches` between the
filename's derived title and the console's catalog) so confirming a correct
guess is a single click — but never applies anything on its own; the full
list and search stay available, and nothing is matched until "Match" is
clicked. `selected_game_id()` returns whatever's selected when that
happens, guess or manual pick alike.
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from retrocheevos.gui import styles
from retrocheevos.library.rom_title import derive_title_from_filename, find_best_title_match
from retrocheevos.models.game import Game

class MatchRomDialog(QDialog):
    """Lists every locally-synced, achievement-bearing game for one console
    (`services/library_service.py::list_games_for_matching`) with a live
    substring filter — cache-only, so filtering as the user types is instant
    even for a console with a large catalog.
    """

    def __init__(
        self,
        file_path: str,
        console_name: str,
        games: list[Game],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Match to Game")
        self.resize(420, 480)
        self._games = sorted(games, key=lambda game: game.title)
        derived_title = derive_title_from_filename(file_path)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"Which {console_name} game is:\n{Path(file_path).name}")
        )

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search games...")
        self._search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_input)

        self._suggestion_label = QLabel("Suggested match highlighted below")
        self._suggestion_label.setStyleSheet(f"color: {styles.TEXT_DIM};")
        self._suggestion_label.setVisible(False)
        layout.addWidget(self._suggestion_label)

        self._game_list = QListWidget()
        for game in self._games:
            item = QListWidgetItem(game.title)
            item.setData(Qt.ItemDataRole.UserRole, game.id)
            self._game_list.addItem(item)
        layout.addWidget(self._game_list)

        self._preselect_suggestion(derived_title)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Match")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _preselect_suggestion(self, derived_title: str) -> None:
        titles = [game.title for game in self._games]
        match = find_best_title_match(derived_title, titles)
        if match is None:
            return
        index = titles.index(match)
        self._game_list.setCurrentRow(index)
        self._game_list.scrollToItem(self._game_list.item(index))
        self._suggestion_label.setVisible(True)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self._game_list.count()):
            item = self._game_list.item(index)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def selected_game_id(self) -> Optional[int]:
        item = self._game_list.currentItem()
        if item is None or item.isHidden():
            return None
        return item.data(Qt.ItemDataRole.UserRole)
