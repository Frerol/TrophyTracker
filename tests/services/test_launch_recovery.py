"""A failed process creation has no play effects; later DB errors are partial success."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from retrocheevos.services import library_service as library, play_session_service as sessions


class LaunchRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        rom_path = Path(temp.name) / 'game.rom'
        rom_path.write_bytes(b'rom')
        self.rom = SimpleNamespace(id=1, file_path=str(rom_path), console_id=1, game_id=2)
        self.connection = MagicMock()
        self.process = MagicMock()
        self.process.poll.return_value = None
        config = SimpleNamespace(executable_path='/fake', arguments_template=None, core_path=None,
                                 flatpak_app_id=None, flatpak_installation=None)
        for patcher in (
            patch.dict(sessions._sessions, {}, clear=True),
            patch.object(library.EmulatorConfigRepository, 'get', return_value=config),
            patch.object(library.GameRepository, 'get_by_id', return_value=SimpleNamespace(title='Game')),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def launch(self):
        return library._launch_installed_rom(self.rom, self.connection, 3)

    def test_process_failure_does_not_change_recency_or_session(self):
        for error in (FileNotFoundError('missing executable'), PermissionError('denied')):
            with self.subTest(error=type(error).__name__), patch.object(library, 'launch_emulator', side_effect=error), patch.object(library.LibraryRepository, 'set_last_played') as recency:
                with self.assertRaises(type(error)):
                    self.launch()
                recency.assert_not_called()
                self.connection.commit.assert_not_called()
                self.assertIsNone(sessions.get_running_session(3))

    def test_metadata_error_happens_before_process_creation(self):
        with patch.object(library.GameRepository, 'get_by_id', side_effect=sqlite3.OperationalError('locked')), patch.object(library, 'launch_emulator') as launch:
            with self.assertRaises(sqlite3.Error):
                self.launch()
            launch.assert_not_called()

    def test_success_records_once_after_process_creation(self):
        order = []
        with patch.object(library, 'launch_emulator', side_effect=lambda *a, **kw: order.append('process') or self.process), patch.object(library.LibraryRepository, 'set_last_played', side_effect=lambda *a: order.append('recency')) as recency, patch.object(sessions, 'record_launch', wraps=sessions.record_launch) as record:
            self.assertIs(self.launch(), self.process)
        self.assertEqual(order, ['process', 'recency'])
        recency.assert_called_once()
        record.assert_called_once()
        self.connection.commit.assert_called_once()
        self.assertIs(sessions.get_running_session(3).process, self.process)

    def test_write_and_commit_failures_return_started_process_and_keep_session(self):
        for phase in ('write', 'commit', 'rollback'):
            with self.subTest(phase=phase):
                self.connection.reset_mock(side_effect=True)
                if phase in ('commit', 'rollback'):
                    self.connection.commit.side_effect = sqlite3.OperationalError('commit failed')
                if phase == 'rollback':
                    self.connection.rollback.side_effect = sqlite3.OperationalError('rollback failed')
                write_error = sqlite3.OperationalError('write failed') if phase == 'write' else None
                with patch.object(library, 'launch_emulator', return_value=self.process) as launch, patch.object(library.LibraryRepository, 'set_last_played', side_effect=write_error), self.assertLogs(library.logger, level='WARNING') as captured:
                    self.assertIs(self.launch(), self.process)
                launch.assert_called_once()
                self.connection.rollback.assert_called_once()
                self.assertIs(sessions.get_running_session(3).process, self.process)
                self.assertIn('Emulator started', '\n'.join(captured.output))
