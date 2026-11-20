"""Argument templates must preserve quoting and native paths."""

import unittest
from pathlib import Path
from unittest.mock import patch

from retrocheevos.library.launcher import build_launch_args, launch_emulator


class LaunchArgumentTests(unittest.TestCase):
    @patch('retrocheevos.library.launcher.subprocess.Popen')
    def test_flatpak_keeps_application_prefix_with_libretro_core(self, popen):
        launch_emulator(
            Path('/usr/bin/flatpak'), Path('/roms/some game.nes'),
            arguments_template='ignored', core_path=Path('/app/lib/core.so'),
            flatpak_app_id='org.libretro.RetroArch', flatpak_installation='user',
        )
        self.assertEqual(popen.call_args.args[0], [
            '/usr/bin/flatpak', 'run', '--user', 'org.libretro.RetroArch',
            '-L', '/app/lib/core.so', '/roms/some game.nes',
        ])

    @patch('retrocheevos.library.launcher.subprocess.Popen')
    def test_flatpak_system_and_named_installations_preserve_arguments(self, popen):
        for installation, flag in (('system', '--system'), ('games', '--installation=games')):
            launch_emulator(
                Path('/usr/bin/flatpak'), Path('/roms/game with spaces.iso'),
                '--fullscreen "{rom_path}"', flatpak_app_id='org.ppsspp.PPSSPP',
                flatpak_installation=installation,
            )
            self.assertEqual(popen.call_args.args[0], [
                '/usr/bin/flatpak', 'run', flag, 'org.ppsspp.PPSSPP',
                '--fullscreen', '/roms/game with spaces.iso',
            ])

    @patch('retrocheevos.library.launcher.subprocess.Popen')
    def test_native_launch_does_not_get_flatpak_prefix(self, popen):
        launch_emulator(Path('/usr/bin/mgba'), Path('/roms/game.gba'))
        self.assertEqual(popen.call_args.args[0], ['/usr/bin/mgba', '/roms/game.gba'])

    @patch('retrocheevos.library.launcher.subprocess.Popen')
    def test_invalid_flatpak_id_is_rejected(self, popen):
        with self.assertRaises(ValueError):
            launch_emulator(Path('/usr/bin/flatpak'), Path('game.gba'), flatpak_app_id='--command=sh')
        popen.assert_not_called()

    def test_quoted_config_and_placeholder(self):
        rom = Path('/roms/some game.gba')
        self.assertEqual(
            build_launch_args(rom, '--config "/some folder/config.ini" "{rom_path}"'),
            ['--config', '/some folder/config.ini', str(rom)],
        )

    def test_windows_backslashes_survive(self):
        self.assertEqual(
            build_launch_args(Path('game.gba'), r'--config "C:\Program Files\Emulator\config.ini" {rom_path}'),
            ['--config', r'C:\Program Files\Emulator\config.ini', 'game.gba'],
        )

    def test_template_without_placeholder_appends_rom(self):
        self.assertEqual(
            build_launch_args(Path('game.gba'), "--label 'my game' --empty \"\""),
            ['--label', 'my game', '--empty', '', 'game.gba'],
        )

    def test_no_template_and_embedded_placeholder(self):
        rom = Path('/roms/some game.gba')
        self.assertEqual(build_launch_args(rom, None), [str(rom)])
        self.assertEqual(build_launch_args(rom, '--rom="{rom_path}"'), ['--rom=' + str(rom)])

    def test_unbalanced_quotes_report_error(self):
        with self.assertRaises(ValueError):
            build_launch_args(Path('game.gba'), '--config "unfinished')
