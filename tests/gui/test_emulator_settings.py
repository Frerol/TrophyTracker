"""Emulators must be configurable offline on a fresh installation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.gui.app_context import AppContext
from retrocheevos.gui.pages.settings_page import SettingsPage
from retrocheevos.models.console import Console
from retrocheevos.models.emulator_discovery import EmulatorCandidate
from retrocheevos.services import console_service, library_service

_app = QApplication.instance() or QApplication([])


class EmulatorSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'fresh.db'
        real_create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: real_create(self.database))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.database).close()
        self.page = SettingsPage(AppContext())
        self.addCleanup(self.page.close)
        self.page.refresh()

    def _select(self, console_id: int) -> None:
        index = self.page._emulator_console_selector.findData(console_id)
        self.assertGreaterEqual(index, 0)
        self.page._emulator_console_selector.setCurrentIndex(index)

    def test_fresh_install_can_select_and_save_without_account_or_sync(self) -> None:
        self.assertEqual(console_service.list_consoles(), [])
        self._select(41)
        self.page._emulator_path_input.setText('/usr/bin/retroarch')
        self.page._emulator_core_input.setText('/cores/ppsspp_libretro.so')
        self.page._on_save_emulator()
        config, = library_service.list_emulator_configs()
        self.assertEqual(config.console_id, 41)
        self.assertEqual(config.executable_path, '/usr/bin/retroarch')
        self.assertEqual(config.core_path, '/cores/ppsspp_libretro.so')
        self.assertEqual(self.page._emulators_list.count(), 1)
        self.assertEqual(self.page._emulator_console_selector.currentData(), 41)

    def test_options_do_not_populate_the_sync_queue(self) -> None:
        options = console_service.list_configurable_consoles()
        self.assertIn(7, {console.id for console in options})
        self.assertEqual(console_service.list_consoles(), [])

    def test_synced_metadata_wins_and_special_collections_are_excluded(self) -> None:
        with db.get_connection() as connection:
            repository = ConsoleRepository(connection)
            repository.upsert(Console(id=41, name='Synced PSP', icon_path='/psp.png'))
            repository.upsert(Console(id=101, name='Events'))
            repository.upsert(Console(id=200, name='Future console'))
        options = {console.id: console for console in console_service.list_configurable_consoles()}
        self.assertEqual(options[41].name, 'Synced PSP')
        self.assertEqual(options[41].icon_path, '/psp.png')
        self.assertIn(200, options)
        self.assertNotIn(101, options)
        library_service.set_emulator_config(41, '/usr/bin/retroarch')
        with db.get_connection() as connection:
            self.assertEqual(ConsoleRepository(connection).get_by_id(41).name, 'Synced PSP')

    def test_rom_folder_can_use_offline_console_reference(self) -> None:
        folder = library_service.add_rom_folder('/roms/nes', console_id=7)
        self.assertEqual(folder.console_id, 7)
        self.assertEqual(len(library_service.list_rom_folders()), 1)
        with db.get_connection() as connection:
            self.assertIsNotNone(ConsoleRepository(connection).get_by_id(7))

    def test_selecting_saved_emulator_loads_fields_and_allows_editing(self) -> None:
        library_service.set_emulator_config(41, '/old/retroarch', '--fullscreen', '/cores/psp.so')
        library_service.set_emulator_config(7, '/usr/bin/nes')
        self.page.refresh()
        self._select(7)
        # The saved list is ordered by console ID; PSP is its second row.
        self.page._emulators_list.setCurrentRow(1)
        self.assertEqual(self.page._emulator_console_selector.currentData(), 41)
        self.assertEqual(self.page._emulator_path_input.text(), '/old/retroarch')
        self.assertEqual(self.page._emulator_args_input.text(), '--fullscreen')
        self.assertEqual(self.page._emulator_core_input.text(), '/cores/psp.so')
        self.page._emulator_path_input.setText('/new/retroarch')
        self.page._on_save_emulator()
        configs = {config.console_id: config for config in library_service.list_emulator_configs()}
        self.assertEqual(configs[41].executable_path, '/new/retroarch')
        self.assertEqual(configs[7].executable_path, '/usr/bin/nes')
        self._select(5)
        self.assertEqual(self.page._emulator_path_input.text(), '')
        self.assertEqual(self.page._emulator_core_input.text(), '')
        self.assertEqual(self.page._emulator_args_input.text(), '')

    def test_removing_saved_emulator_clears_its_form(self) -> None:
        library_service.set_emulator_config(41, '/usr/bin/retroarch')
        self.page.refresh()
        self._select(41)
        self.page._remove_emulator(41)
        self.assertEqual(library_service.list_emulator_configs(), [])
        self.assertEqual(self.page._emulator_path_input.text(), '')

    def test_discovery_fills_path_and_waits_for_save(self) -> None:
        self._select(41)
        with patch('retrocheevos.gui.pages.settings_page.FindEmulatorDialog') as factory:
            factory.return_value.exec.return_value = QDialog.DialogCode.Accepted
            factory.return_value.selected_candidate = EmulatorCandidate('PPSSPP', '/apps/PPSSPP.AppImage')
            self.page._on_find_emulator()
        self.assertEqual(self.page._emulator_path_input.text(), '/apps/PPSSPP.AppImage')
        self.assertEqual(library_service.list_emulator_configs(), [])
        self.page._on_save_emulator()
        self.assertEqual(library_service.list_emulator_configs()[0].executable_path, '/apps/PPSSPP.AppImage')

    def test_cancel_discovery_preserves_current_path(self) -> None:
        self._select(41)
        self.page._emulator_path_input.setText('/existing/emulator')
        with patch('retrocheevos.gui.pages.settings_page.FindEmulatorDialog') as factory:
            factory.return_value.exec.return_value = QDialog.DialogCode.Rejected
            self.page._on_find_emulator()
        self.assertEqual(self.page._emulator_path_input.text(), '/existing/emulator')
