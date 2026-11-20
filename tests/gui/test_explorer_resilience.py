"""Debouncing, cover recovery and bounded long browsing in Explorer."""
import unittest
from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt, QPersistentModelIndex
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from retrocheevos.core.explorer import GameWithCompletion
from retrocheevos.gui.models import explorer_table_model as models
from retrocheevos.gui.pages import explorer_page
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.workers import WorkerRegistry
from retrocheevos.services.explorer_service import ExplorerSnapshot
from retrocheevos.models.game import Game

_app = QApplication.instance() or QApplication([])


class ExplorerResilienceTests(unittest.TestCase):
    def test_failure_expires_and_repaints_without_interaction(self):
        loader = Mock()
        model = models.ExplorerTableModel(loader)
        game = Game(1, 'Game', 1, True)
        model.set_data([GameWithCompletion(game, None)], {}, set())
        changed = []
        model.dataChanged.connect(lambda *_: changed.append(True))
        with patch.object(models.time, 'monotonic', return_value=10):
            model._pixmap_for(game)
            model._on_image_ready(game.id, None)
            model._pixmap_for(game)
            self.assertEqual(loader.request.call_count, 1)
        changed.clear()
        with patch.object(models.time, 'monotonic', return_value=41):
            model._expire_failures()
            self.assertTrue(changed)
            model._pixmap_for(game)
            self.assertEqual(loader.request.call_count, 2)
            pixmap = QPixmap(40, 40)
            pixmap.fill(Qt.GlobalColor.red)
            model._on_image_ready(game.id, pixmap)
            self.assertIsNotNone(model._pixmap_for(game))
        self.assertFalse(model._retry_timer.isActive())

    def test_long_browsing_bounds_pixels_and_failure_metadata(self):
        model = models.ExplorerTableModel(Mock())
        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.red)
        for key in range(model._max_image_cache + 100):
            model._on_image_ready(key, pixmap)
        pixel_bytes = sum(p.width() * p.height() * p.depth() // 8 for p in model._image_cache.values())
        self.assertLessEqual(pixel_bytes, models.IMAGE_CACHE_BYTES)
        for key in range(models.MAX_IMAGE_FAILURES + 100):
            model._on_image_ready(key, None)
        self.assertLessEqual(len(model._image_failures), models.MAX_IMAGE_FAILURES)
        model._retry_timer.stop()

    def test_typing_is_coalesced_in_both_instances_and_enter_cancels_timer(self):
        registry = WorkerRegistry()
        context = SimpleNamespace(active_account=SimpleNamespace(id=1), workers=registry, create_image_loader=ImageLoader)
        with patch.object(explorer_page.explorer_service, 'get_snapshot', return_value=ExplorerSnapshot([], 0, set())) as query, \
             patch.object(explorer_page.explorer_service, 'get_total_game_count', return_value=0), \
             patch.object(explorer_page.library_service, 'get_installed_game_ids', return_value=set()):
            pages = [explorer_page.ExplorerPage(context), explorer_page.ExplorerPage(context)]
            try:
                for page in pages:
                    for text in ('m', 'ma', 'mar', 'mario'):
                        page.set_search_text(text)
                self.assertEqual(query.call_count, 0)
                QTest.qWait(220)
                self.assertEqual(query.call_count, 2)
                self.assertEqual(query.call_args.args[1].search_text, 'mario')
                pages[0]._search_input.setText('zelda')
                pages[0]._search_input.returnPressed.emit()
                QTest.qWait(220)
                self.assertEqual(query.call_count, 3)
            finally:
                registry.shutdown()
                for page in pages:
                    page.close()

    def test_slow_read_keeps_gui_live_and_only_latest_search_is_applied(self):
        registry = WorkerRegistry()
        context = SimpleNamespace(active_account=SimpleNamespace(id=1), workers=registry, create_image_loader=ImageLoader)
        started, release = Event(), Event()
        old = ExplorerSnapshot([GameWithCompletion(Game(1, 'Old', 1, True), None)], 1, set())
        latest = ExplorerSnapshot([GameWithCompletion(Game(2, 'Latest', 1, True), None)], 1, set())

        def read(_account_id, filters):
            if filters.search_text == 'old':
                started.set()
                release.wait(3)
                return old
            return latest

        with patch.object(explorer_page.explorer_service, 'get_snapshot', side_effect=read) as query:
            page = explorer_page.ExplorerPage(context)
            try:
                page.set_search_text('old')
                page._refresh_results()
                for _ in range(100):
                    if started.is_set():
                        break
                    QTest.qWait(5)
                self.assertTrue(started.is_set())
                page.set_search_text('intermediate')
                page._refresh_results()
                page.set_search_text('latest')
                page._refresh_results()
                self.assertEqual(query.call_count, 1)
                release.set()
                for _ in range(100):
                    if page._read_worker is None:
                        break
                    QTest.qWait(5)
                self.assertEqual(query.call_count, 2)
                self.assertEqual([r.game.id for r in page._current_results], [2])
                context.active_account = None
                page._refresh_results()
                page._apply_snapshot(page._read_generation - 1, 1, old)
                self.assertEqual(page._table_model.rowCount(), 0)
            finally:
                release.set()
                registry.shutdown()
                page.close()

    def test_sorting_preserves_numeric_values_selection_and_refresh_order(self):
        model = models.ExplorerTableModel(Mock())
        first = GameWithCompletion(Game(1, 'Zelda', 1, True, median_time_to_beat_hardcore_seconds=600), 75)
        second = GameWithCompletion(Game(2, 'Mario', 2, True, median_time_to_beat_hardcore_seconds=120), 5)
        third = GameWithCompletion(Game(3, 'Unknown', 1, True), None)
        rows = [first, second, third]
        model.set_data(rows, {1: 'NES', 2: 'SNES'}, {1})
        selected = QPersistentModelIndex(model.index(0, models.COLUMN_TITLE))
        self.assertEqual(selected.data(), 'Mario')
        for column, expected in ((models.COLUMN_TITLE, [2, 3, 1]),
                                 (models.COLUMN_MEDIAN_TIME, [3, 2, 1]),
                                 (models.COLUMN_PROGRESS, [3, 2, 1]),
                                 (models.COLUMN_INSTALLED, [3, 2, 1])):
            model.sort(column, Qt.SortOrder.AscendingOrder)
            self.assertEqual([r.game.id for r in model._results], expected)
            self.assertEqual(selected.data(), 'Mario')
        model.sort(models.COLUMN_PROGRESS, Qt.SortOrder.DescendingOrder)
        model.set_data(rows, {}, set())
        self.assertEqual([r.game.id for r in model._results], [1, 2, 3])
        self.assertEqual(rows, [first, second, third])

    def test_worker_exception_releases_pending_and_allows_retry(self):
        loader = ImageLoader()
        game = Game(42, 'Game', 1, True)
        received = []
        loader.image_ready.connect(lambda *args: received.append(args))
        with patch('retrocheevos.gui.image_loader.ensure_game_image_cached', side_effect=RuntimeError('offline')):
            loader.request(game)
            for _ in range(100):
                if received and not loader._pending and not loader._tasks:
                    break
                QTest.qWait(10)
        self.assertEqual(received, [(42, None)])
        self.assertFalse(loader._pending)
        self.assertFalse(loader._tasks)
        with patch('retrocheevos.gui.image_loader.ensure_game_image_cached', return_value=None) as retry:
            loader.request(game)
            for _ in range(100):
                if len(received) == 2 and not loader._tasks:
                    break
                QTest.qWait(10)
            self.assertEqual(retry.call_count, 1)
            self.assertEqual(len(received), 2)
        loader.shutdown()
