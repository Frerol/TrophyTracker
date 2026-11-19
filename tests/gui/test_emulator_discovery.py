"""Discovery stays asynchronous and the console popup remains scrollable."""

import time
import unittest
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from retrocheevos.gui.dialogs.find_emulator_dialog import FindEmulatorDialog
from retrocheevos.gui.styles import APP_STYLESHEET
from retrocheevos.models.emulator_discovery import EmulatorCandidate, EmulatorSearchResult
from retrocheevos.services import emulator_discovery_service
from retrocheevos.widgets.console_selector import ConsoleSelector, POPUP_MAX_HEIGHT

_app = QApplication.instance() or QApplication([])


def wait_until(predicate) -> None:
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('timed out waiting for background search')
        QTest.qWait(5)


class EmulatorDiscoveryDialogTests(unittest.TestCase):
    def test_results_require_explicit_selection_and_acceptance(self) -> None:
        candidate = EmulatorCandidate('PPSSPP', '/apps/PPSSPP.AppImage')
        def search(_console, result_callback, **_kwargs):
            result_callback(candidate)
            return EmulatorSearchResult([candidate])
        with patch.object(emulator_discovery_service, 'find_emulators', side_effect=search):
            dialog = FindEmulatorDialog(41, 'PSP')
            dialog.show()
            try:
                wait_until(lambda: dialog._results.count() == 1 and dialog._worker is None)
                self.assertIsNone(dialog.selected_candidate)
                self.assertTrue(dialog._use_button.isEnabled())
                dialog.accept()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                self.assertEqual(dialog.selected_candidate, candidate)
            finally:
                dialog.reject()

    def test_cancel_waits_for_worker_to_finish_without_blocking_gui(self) -> None:
        started = Event()
        def search(_console, stop_requested, **_kwargs):
            started.set()
            while not stop_requested():
                started.wait(0.01)
                time.sleep(0.005)
            return EmulatorSearchResult(cancelled=True)
        with patch.object(emulator_discovery_service, 'find_emulators', side_effect=search):
            dialog = FindEmulatorDialog(41, 'PSP')
            dialog.show()
            try:
                wait_until(started.is_set)
                self.assertFalse(dialog._use_button.isEnabled())
                dialog.reject()
                wait_until(lambda: dialog._worker is None)
                self.assertFalse(dialog.isVisible())
                self.assertIsNone(dialog.selected_candidate)
            finally:
                dialog.reject()
                wait_until(lambda: dialog._worker is None)

    def test_error_restores_controls(self) -> None:
        with patch.object(emulator_discovery_service, 'find_emulators', side_effect=OSError('disk unavailable')):
            dialog = FindEmulatorDialog(41, 'PSP')
            dialog.show()
            try:
                wait_until(lambda: 'Search failed' in dialog._status.text() and dialog._worker is None)
                self.assertTrue(dialog._folder_button.isEnabled())
                self.assertTrue(dialog._common_button.isEnabled())
            finally:
                dialog.reject()


class ConsolePopupTests(unittest.TestCase):
    def test_large_console_list_has_bounded_popup_and_reachable_last_item(self) -> None:
        combo = ConsoleSelector()
        combo.setStyleSheet(APP_STYLESHEET + '\n' + combo.styleSheet())
        for console_id in range(82):
            combo.addItem(f'Console {console_id}', console_id)
        combo.show()
        combo.showPopup()
        try:
            _app.processEvents()
            self.assertLessEqual(combo.view().height(), POPUP_MAX_HEIGHT)
            self.assertLessEqual(combo.view().window().height(), POPUP_MAX_HEIGHT + 20)
            scrollbar = combo.view().verticalScrollBar()
            self.assertGreater(scrollbar.maximum(), 0)
            scrollbar.setValue(scrollbar.maximum())
            combo.setCurrentIndex(81)
            self.assertEqual(combo.currentData(), 81)
            self.assertEqual(combo.view().verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        finally:
            combo.hidePopup()
            combo.close()
