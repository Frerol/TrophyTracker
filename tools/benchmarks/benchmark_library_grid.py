"""Measure the Library cover grid (R22) with a synthetic 2,000-game library.

Run from the repository root:

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/benchmarks/benchmark_library_grid.py

No database, network or personal data: entries are synthetic and cover
loads are answered in-process with a solid pixmap.
"""

import json
import statistics
import time
from unittest.mock import patch

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListView

ENTRIES = 2000
VIEWPORT = QSize(956, 560)  # Library grid at a 1240×780 window
SCROLL_STEPS = 40


class _Loader(QObject):
    image_ready = Signal(int, object)
    rom_image_ready = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self.requests = 0

    def request(self, _game) -> None:
        self.requests += 1

    def request_rom(self, _rom, _cover_game=None) -> None:
        self.requests += 1


def main() -> None:
    app = QApplication.instance() or QApplication([])
    from retrocheevos.gui.assets import load_bundled_fonts
    from retrocheevos.gui.delegates.library_card_delegate import CELL_HEIGHT, LibraryCardDelegate
    from retrocheevos.gui.models import library_grid_model
    from retrocheevos.gui.models.library_grid_model import LibraryGridModel
    from retrocheevos.gui.styles import apply_theme
    from retrocheevos.models.game import Game
    from retrocheevos.models.library import LibraryEntry

    load_bundled_fonts()
    apply_theme(app)
    entries = [
        LibraryEntry(
            "game", f"Game {i:04d} with a reasonably long title", 3, [f"/roms/{i}.sfc"],
            game=Game(i, f"Game {i}", 3, True), achievements_unlocked=i % 40,
            achievements_total=40, has_emulator=i % 7 != 0,
        )
        for i in range(1, ENTRIES + 1)
    ]
    with patch.object(library_grid_model, "cached_local_cover_path", return_value="/nonexistent"):
        loader = _Loader()
        model = LibraryGridModel(loader)
        view = QListView()
        delegate = LibraryCardDelegate(view)
        view.setModel(model)
        view.setItemDelegate(delegate)
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setUniformItemSizes(True)
        view.setMovement(QListView.Movement.Static)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.resize(VIEWPORT)
        cell = QSize(VIEWPORT.width() // 4 - 1, CELL_HEIGHT)
        delegate.set_cell_size(cell)
        view.setGridSize(cell)
        view.show()
        QTest.qWait(50)

        start = time.perf_counter()
        model.set_entries(entries, {3: "SNES"})
        view.viewport().grab()
        first_paint = (time.perf_counter() - start) * 1000

        cover = QPixmap(256, 256)
        cover.fill(Qt.GlobalColor.red)
        frames = []
        for step in range(SCROLL_STEPS):
            view.verticalScrollBar().setValue(step * 400)
            for game_id in range(1, ENTRIES + 1):
                if ("game", game_id) in model._pending:
                    loader.image_ready.emit(game_id, cover)
            start = time.perf_counter()
            view.viewport().grab()
            frames.append((time.perf_counter() - start) * 1000)

        print(json.dumps({
            "entries": ENTRIES,
            "reset_and_first_paint_ms": round(first_paint, 1),
            "scroll_paint_ms_median": round(statistics.median(frames), 2),
            "scroll_paint_ms_max": round(max(frames), 2),
            "cover_requests": loader.requests,
            "cached_cover_bytes": model.cached_bytes(),
            "cover_budget_bytes": library_grid_model.IMAGE_CACHE_BYTES,
        }, indent=2))
        view.close()


if __name__ == "__main__":
    main()
