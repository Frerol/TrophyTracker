"""Reproducible R05/R06/R07 probe. Run with QT_QPA_PLATFORM=offscreen PYTHONPATH=src.

Uses only a temporary synthetic database and mocked artwork; no account data/network.
"""
from contextlib import ExitStack
import json
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from retrocheevos.database import connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.gui.models.explorer_table_model import ExplorerTableModel, IMAGE_CACHE_BYTES
from retrocheevos.gui.pages import explorer_page
from retrocheevos.gui.image_loader import ImageLoader
from retrocheevos.gui.workers import WorkerRegistry

CATALOG_SIZE = 13327


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / 'benchmark.db'
        conn = initialize_database(path)
        conn.execute("INSERT INTO accounts(id, username, api_key) VALUES(1, 'benchmark', '')")
        conn.execute("INSERT INTO consoles(id, name) VALUES(1, 'Benchmark')")
        conn.executemany(
            "INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, 1, 1)",
            ((i, f'Game {i:05d}') for i in range(1, CATALOG_SIZE + 1)),
        )
        conn.executemany('INSERT INTO game_hashes(game_id, hash) VALUES(?, ?)',
                         ((i, f'{i:032x}') for i in range(1, CATALOG_SIZE + 1)))
        conn.executemany('INSERT INTO game_completion(account_id, game_id, percent_complete) VALUES(1, ?, 25)',
                         ((i,) for i in range(1, CATALOG_SIZE + 1)))
        conn.commit()
        hashes = [f'{i:032x}' for i in range(1, CATALOG_SIZE, 27)]
        times = {}
        for label, lookup in (
            ('previous', lambda value: conn.execute('SELECT game_id FROM game_hashes WHERE LOWER(hash) = LOWER(?)', (value,)).fetchone()),
            ('indexed', GameRepository(conn).find_game_id_by_hash),
        ):
            start = time.perf_counter()
            for value in hashes:
                lookup(value)
            times[label] = round((time.perf_counter() - start) * 1000, 2)
        plan = conn.execute('EXPLAIN QUERY PLAN SELECT game_id FROM game_hashes WHERE hash = ?', (hashes[0],)).fetchone()[3]
        conn.close()
        queries = []
        real_create = db.create_connection

        def create(database_path=None):
            connection = real_create(path)
            connection.set_trace_callback(lambda sql: queries.append(sql) if sql.lstrip().upper().startswith('SELECT') else None)
            return connection

        with ExitStack() as cleanup, \
             patch.object(db, 'create_connection', side_effect=create), \
             patch.object(ImageLoader, 'request'):
            registry = WorkerRegistry()
            cleanup.callback(registry.shutdown)
            context = SimpleNamespace(active_account=SimpleNamespace(id=1), workers=registry, create_image_loader=ImageLoader)
            page = explorer_page.ExplorerPage(context)
            cleanup.callback(page.close)
            page._console_names = {1: 'Benchmark'}
            page.resize(1000, 700)
            page.show()
            app.processEvents()
            query_counts, refresh_times, input_times = [], [], []
            ticks = []
            heartbeat = QTimer()
            heartbeat.setInterval(5)
            heartbeat.timeout.connect(lambda: ticks.append(time.perf_counter()))
            heartbeat.start()

            def wait_for_read():
                deadline = time.monotonic() + 10
                while page._search_debounce_timer.isActive() or page._read_worker is not None:
                    if time.monotonic() > deadline:
                        raise RuntimeError('Explorer read timed out')
                    app.processEvents()
                    time.sleep(0.001)
            for i in range(5):
                page._search_input.setText('Game' if i % 2 else 'Game ')
                queries.clear()
                start = time.perf_counter()
                page._refresh_results()
                wait_for_read()
                page._table.viewport().repaint()
                app.processEvents()
                refresh_times.append((time.perf_counter() - start) * 1000)
                query_counts.append(len(queries))
            queries.clear()
            start = time.perf_counter()
            for text in ('G', 'Ga', 'Gam', 'Game'):
                page.set_search_text(text)
            wait_for_read()
            page._table.viewport().repaint()
            app.processEvents()
            input_times.append((time.perf_counter() - start) * 1000)
            burst_queries = len(queries)
            rows = page._table_model.rowCount()
            heartbeat.stop()
            registry.shutdown()
            page.close()
        model = ExplorerTableModel(SimpleNamespace(image_ready=SimpleNamespace(connect=lambda _: None)))
        pixmap = QPixmap(100, 100)
        for key in range(CATALOG_SIZE):
            model._on_image_ready(key, pixmap)
        pixel_bytes = sum(p.width() * p.height() * p.depth() // 8 for p in model._image_cache.values())
        print(json.dumps({
            'sqlite': sqlite3.sqlite_version, 'catalog_games_and_hashes': CATALOG_SIZE,
            'bulk_hash_lookups': len(hashes), 'bulk_hash_ms': times, 'query_plan': plan,
            'explorer_rows': rows, 'refresh_select_counts': query_counts,
            'refresh_render_ms_median': round(statistics.median(refresh_times), 2),
            'refresh_render_ms_max': round(max(refresh_times), 2),
            'burst_input_to_render_ms': round(input_times[0], 2),
            'four_keystroke_burst_selects': burst_queries,
            'gui_heartbeat_max_gap_ms': round(max((b-a)*1000 for a,b in zip(ticks, ticks[1:])), 2),
            'cached_pixel_bytes_after_browsing': pixel_bytes,
            'pixel_budget_bytes_per_model': IMAGE_CACHE_BYTES,
        }, indent=2))


if __name__ == '__main__':
    main()
