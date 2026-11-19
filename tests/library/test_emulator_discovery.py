"""Local searches find launchable emulators without traversing unbounded trees."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrocheevos.library import emulator_discovery as discovery


class EmulatorDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def _file(self, name: str, executable: bool = True) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nexit 0\n')
        path.chmod(0o755 if executable else 0o644)
        return path

    def test_console_filter_and_versioned_portable_builds(self) -> None:
        retroarch = self._file('bin/retroarch')
        pcsx2 = self._file('Emulators/PCSX2-v2.4.0-linux-appimage-x64-Qt.AppImage')
        self._file('Emulators/PPSSPP.AppImage')
        self._file('other/pcsx2-updater')
        self._file('other/pcsx2-v2.4.0-setup.AppImage')
        self._file('other/pcsx2-v2.4.0.dll')
        self._file('other/pcsx2-qt', executable=False)
        with patch.object(discovery.sys, 'platform', 'linux'):
            psp = discovery.discover_emulators(41, [self.root])
            ps2 = discovery.discover_emulators(21, [self.root])
        self.assertEqual({candidate.name for candidate in psp.candidates}, {'RetroArch', 'PPSSPP'})
        self.assertEqual({candidate.executable_path for candidate in ps2.candidates}, {str(pcsx2), str(retroarch)})
        self.assertTrue(next(candidate for candidate in psp.candidates if candidate.executable_path == str(retroarch)).requires_core)

    def test_linux_dolphin_file_manager_is_not_an_emulator(self) -> None:
        self._file('dolphin')
        emulator = self._file('dolphin-emu')
        with patch.object(discovery.sys, 'platform', 'linux'):
            result = discovery.discover_emulators(16, [self.root])
        self.assertEqual([candidate.executable_path for candidate in result.candidates], [str(emulator)])

    def test_windows_executable_names_and_installers(self) -> None:
        emulator = self._file('Portable/PPSSPPWindows64.exe')
        self._file('PPSSPPWindows64.dll')
        self._file('PPSSPPWindows64-setup.exe')
        self._file('PPSSPPWindows64')
        with patch.object(discovery.sys, 'platform', 'win32'):
            result = discovery.discover_emulators(41, [self.root])
        self.assertEqual([candidate.executable_path for candidate in result.candidates], [str(emulator)])

    @unittest.skipIf(os.name == 'nt', 'requires POSIX symlinks')
    def test_duplicate_roots_and_symlink_targets_are_deduplicated(self) -> None:
        real = self._file('bin/retroarch')
        (self.root / 'RetroArch.AppImage').symlink_to(real)
        external = self.root / 'outside'
        self._file('outside/PPSSPP.AppImage')
        inside = self.root / 'bin'
        (inside / 'linked-folder').symlink_to(external, target_is_directory=True)
        streamed = []
        with patch.object(discovery.sys, 'platform', 'linux'):
            result = discovery.discover_emulators(41, [inside, inside], result_callback=streamed.append)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(streamed, result.candidates)
        with patch.object(discovery.sys, 'platform', 'linux'):
            result = discovery.discover_emulators(41, [self.root])
        self.assertEqual(len([candidate for candidate in result.candidates if candidate.name == 'RetroArch']), 1)

    def test_cancel_before_start_and_after_first_result(self) -> None:
        self._file('retroarch')
        self._file('PPSSPP.AppImage')
        cancelled = discovery.discover_emulators(41, [self.root], stop_requested=lambda: True)
        self.assertTrue(cancelled.cancelled)
        self.assertEqual(cancelled.candidates, [])
        streamed = []
        with patch.object(discovery.sys, 'platform', 'linux'):
            result = discovery.discover_emulators(
                41, [self.root], stop_requested=lambda: bool(streamed), result_callback=streamed.append
            )
        self.assertTrue(result.cancelled)
        self.assertEqual(len(result.candidates), 1)

    def test_missing_and_unreadable_directories_do_not_abort_search(self) -> None:
        self._file('accessible/retroarch')
        blocked = self.root / 'blocked'
        real_scandir = os.scandir
        def scandir(path):
            if Path(path) == blocked:
                raise PermissionError('unreadable')
            return real_scandir(path)
        with patch.object(discovery.os, 'scandir', side_effect=scandir), patch.object(discovery.sys, 'platform', 'linux'):
            result = discovery.discover_emulators(41, [blocked, self.root / 'missing', self.root / 'accessible'])
        self.assertEqual(len(result.candidates), 1)

    def test_time_and_directory_budgets_limit_search(self) -> None:
        self._file('subdir/retroarch')
        with patch.object(discovery, 'MAX_DIRECTORIES', 1):
            self.assertTrue(discovery.discover_emulators(41, [self.root]).limited)
        with patch.object(discovery.time, 'monotonic', side_effect=[0, 31]):
            self.assertTrue(discovery.discover_emulators(41, [self.root]).limited)

    def test_unknown_console_does_not_return_unrelated_emulators(self) -> None:
        self._file('retroarch')
        self.assertEqual(discovery.discover_emulators(999, [self.root]).candidates, [])
