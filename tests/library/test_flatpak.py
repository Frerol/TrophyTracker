"""Flatpak discovery respects installations, consoles, cancellation and host libraries."""

import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from retrocheevos.library import flatpak
from retrocheevos.library.process_environment import host_process_environment


class FlatpakDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.process = MagicMock()
        self.process.__enter__.return_value = self.process
        self.process.returncode = 0
        self.process.communicate.return_value = ('', '')
        for patcher in (
            patch.object(flatpak.sys, 'platform', 'linux'),
            patch.object(flatpak.shutil, 'which', return_value='/usr/bin/flatpak'),
            patch.object(flatpak.subprocess, 'Popen', return_value=self.process),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_user_and_system_are_distinct_and_duplicates_are_removed(self) -> None:
        self.process.communicate.return_value = (
            'org.ppsspp.PPSSPP\tuser\norg.ppsspp.PPSSPP\tsystem\n'
            'org.ppsspp.PPSSPP\tuser\norg.DolphinEmu.dolphin-emu\tuser\n'
            'org.kde.dolphin\tsystem\norg.freedesktop.Platform\tsystem\nmalformed\n', ''
        )
        streamed = []
        result = flatpak.discover_flatpaks(41, result_callback=streamed.append)
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual({item.flatpak_installation for item in result.candidates}, {'user', 'system'})
        self.assertTrue(all(item.flatpak_app_id == 'org.ppsspp.PPSSPP' for item in result.candidates))
        self.assertEqual(streamed, result.candidates)
        self.assertEqual(flatpak.subprocess.Popen.call_args.args[0], [
            '/usr/bin/flatpak', 'list', '--app', '--columns=application,installation'
        ])

    def test_retroarch_has_core_marker_and_named_installation(self) -> None:
        self.process.communicate.return_value = ('org.libretro.RetroArch\tgames\n', '')
        result = flatpak.discover_flatpaks(7)
        self.assertTrue(result.candidates[0].requires_core)
        self.assertEqual(result.candidates[0].flatpak_installation, 'games')

    def test_dolphin_flatpak_does_not_conflict_with_kde_file_manager(self) -> None:
        self.process.communicate.return_value = ('org.DolphinEmu.dolphin-emu\tuser\norg.kde.dolphin\tsystem\n', '')
        result = flatpak.discover_flatpaks(16)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].name, 'Dolphin')

    def test_missing_flatpak_and_other_platforms_skip_query(self) -> None:
        with patch.object(flatpak.shutil, 'which', return_value=None):
            self.assertEqual(flatpak.discover_flatpaks(41).candidates, [])
        with patch.object(flatpak.sys, 'platform', 'win32'):
            self.assertEqual(flatpak.discover_flatpaks(41).candidates, [])
        flatpak.subprocess.Popen.assert_not_called()

    def test_cancelled_query_stops_subprocess(self) -> None:
        self.process.communicate.side_effect = [subprocess.TimeoutExpired('flatpak', 0.1), ('', '')]
        result = flatpak.discover_flatpaks(41, stop_requested=MagicMock(side_effect=[False, False, True]))
        self.assertTrue(result.cancelled)
        self.process.kill.assert_called_once()

    def test_timeout_stops_subprocess_and_reports_warning(self) -> None:
        with patch.object(flatpak, 'LIST_TIMEOUT_SECONDS', -1):
            result = flatpak.discover_flatpaks(41)
        self.assertTrue(result.limited)
        self.assertTrue(result.warnings)
        self.process.kill.assert_called_once()

    def test_query_failure_reports_warning(self) -> None:
        self.process.returncode = 1
        self.process.communicate.return_value = ('', 'failure')
        self.assertTrue(flatpak.discover_flatpaks(41).warnings)


class HostEnvironmentTests(unittest.TestCase):
    def test_frozen_environment_restores_host_libraries_without_global_changes(self) -> None:
        environment = {
            'LD_LIBRARY_PATH': '/bundle/libs', 'LD_LIBRARY_PATH_ORIG': '/host/libs',
            'QT_PLUGIN_PATH': '/bundle/qt', 'QT_QPA_PLATFORM_PLUGIN_PATH': '/bundle/platforms',
            'DISPLAY': ':0',
        }
        with patch.dict(os.environ, environment, clear=True), patch('sys.frozen', True, create=True), patch('sys.platform', 'linux'):
            result = host_process_environment()
            self.assertEqual(result['LD_LIBRARY_PATH'], '/host/libs')
            self.assertNotIn('QT_PLUGIN_PATH', result)
            self.assertNotIn('QT_QPA_PLATFORM_PLUGIN_PATH', result)
            self.assertEqual(result['DISPLAY'], ':0')
            self.assertEqual(os.environ['LD_LIBRARY_PATH'], '/bundle/libs')

    def test_frozen_environment_removes_bundled_library_path_without_original(self) -> None:
        with patch.dict(os.environ, {'LD_LIBRARY_PATH': '/bundle'}, clear=True), patch('sys.frozen', True, create=True), patch('sys.platform', 'linux'):
            self.assertNotIn('LD_LIBRARY_PATH', host_process_environment())
