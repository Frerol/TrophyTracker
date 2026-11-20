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

    def test_flatpak_selection_survives_save_reload_and_native_replacement(self) -> None:
        self._select(41)
        with patch('retrocheevos.gui.pages.settings_page.FindEmulatorDialog') as factory:
            factory.return_value.exec.return_value = QDialog.DialogCode.Accepted
            factory.return_value.selected_candidate = EmulatorCandidate(
                'PPSSPP', '/usr/bin/flatpak', flatpak_app_id='org.ppsspp.PPSSPP',
                flatpak_installation='user',
            )
            self.page._on_find_emulator()
        self.assertIn('org.ppsspp.PPSSPP', self.page._emulator_flatpak_info.text())
        self.page._on_save_emulator()
        config, = library_service.list_emulator_configs()
        self.assertEqual(config.flatpak_app_id, 'org.ppsspp.PPSSPP')
        self.assertEqual(config.flatpak_installation, 'user')
        self._select(5)
        self.assertIsNone(self.page._flatpak_app_id)
        self._select(41)
        self.assertEqual(self.page._flatpak_app_id, 'org.ppsspp.PPSSPP')
        with patch('retrocheevos.gui.pages.settings_page.QFileDialog.getOpenFileName', return_value=('/apps/PPSSPP.AppImage', '')):
            self.page._on_browse_emulator()
        self.page._on_save_emulator()
        config, = library_service.list_emulator_configs()
        self.assertIsNone(config.flatpak_app_id)
        self.assertIsNone(config.flatpak_installation)

    def test_saved_flatpak_launch_is_forwarded_from_library(self) -> None:
        path = self.database.parent / 'game with spaces.iso'
        path.write_bytes(b'game')
        library_service.set_emulator_config(
            41, '/usr/bin/flatpak', '--fullscreen "{rom_path}"',
            flatpak_app_id='org.ppsspp.PPSSPP', flatpak_installation='user',
        )
        rom = library_service.record_installed_rom(str(path), 41, 'hash')
        with patch.object(library_service, 'create_connection', side_effect=lambda: db.create_connection()), patch('retrocheevos.library.launcher.subprocess.Popen') as popen:
            library_service.launch_installed_rom(rom.id)
        self.assertEqual(popen.call_args.args[0], [
            str(Path('/usr/bin/flatpak')), 'run', '--user', 'org.ppsspp.PPSSPP',
            '--fullscreen', str(path),
        ])

    def test_switch_to_flatpak_retroarch_requires_choosing_its_core(self) -> None:
        self._select(7)
        self.page._emulator_core_input.setText('/native/core.so')
        with patch('retrocheevos.gui.pages.settings_page.FindEmulatorDialog') as factory:
            factory.return_value.exec.return_value = QDialog.DialogCode.Accepted
            factory.return_value.selected_candidate = EmulatorCandidate(
                'RetroArch', '/usr/bin/flatpak', requires_core=True,
                flatpak_app_id='org.libretro.RetroArch', flatpak_installation='system',
            )
            self.page._on_find_emulator()
        self.assertEqual(self.page._emulator_core_input.text(), '')
        self.page._emulator_core_input.setText('/app/lib/core.so')
        self.page._on_save_emulator()
        self.assertEqual(library_service.list_emulator_configs()[0].core_path, '/app/lib/core.so')
