"""Argument templates must preserve quoting and native paths."""

import unittest
from pathlib import Path

from retrocheevos.library.launcher import build_launch_args


class LaunchArgumentTests(unittest.TestCase):
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
