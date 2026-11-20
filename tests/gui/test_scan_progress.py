"""Discovery progress reaches Library without flooding the GUI event queue."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel

from retrocheevos.gui import workers
from retrocheevos.gui.pages.library_page import LibraryPage

_app = QApplication.instance() or QApplication([])


class ScanProgressTests(unittest.TestCase):
    def test_scan_progress_uses_path_signal_and_throttles_fast_discovery(self):
        def scan(progress_callback):
            for count in range(3):
                progress_callback(count, f'/roms/{count}')

        worker = workers.ServiceWorker(scan, report_scan_progress=True)
        events = []
        worker.scan_progress.connect(lambda *args: events.append(args))
        with patch.object(workers.time, 'monotonic', side_effect=[0.0, 0.001, 0.2]):
            worker.run()
        self.assertEqual(events, [(0, '/roms/0'), (2, '/roms/2')])
        label = QLabel()
        LibraryPage._on_scan_progress(SimpleNamespace(_scan_status_label=label), 2, '/roms/2')
        self.assertIn('Discovered 2 entries', label.text())
        self.assertIn('/roms/2', label.text())
