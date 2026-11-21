"""Exercise the relocated spec's inputs without building or replacing artifacts."""

import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

SPEC = Path(__file__).resolve().parents[1] / 'packaging' / 'TrophyTracker.spec'


class PackagingPathsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # resolve(): Windows temp dirs may be 8.3 short paths (RUNNER~1).
        self.root = Path(temporary.name).resolve() / 'project'
        for directory in ('packaging', 'src/retrocheevos', 'assets', 'assets/reference', 'tools/rahasher'):
            (self.root / directory).mkdir(parents=True)
        for file in ('src/retrocheevos/main.py', 'assets/icon.png', 'assets/logo.png',
                     'assets/reference/historical.png'):
            (self.root / file).touch()
        self.helper = self.root / 'tools' / 'rahasher'
        self.binary = self.helper / ('RAHasher.exe' if sys.platform == 'win32' else 'RAHasher')
        self.analysis = Mock(return_value=SimpleNamespace(
            pure=[], zipped_data=[], scripts=[], binaries=[], datas=[],
        ))
        self.modules = {name: ModuleType(name) for name in (
            'PyInstaller', 'PyInstaller.building', 'PyInstaller.building.api',
            'PyInstaller.building.build_main',
        )}
        self.modules['PyInstaller.building.build_main'].Analysis = self.analysis
        for name in ('COLLECT', 'EXE', 'PYZ'):
            setattr(self.modules['PyInstaller.building.api'], name, Mock())

    def execute_spec(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root.parent)
            with patch.dict(sys.modules, self.modules):
                runpy.run_path(str(SPEC), init_globals={'SPECPATH': str(self.root / 'packaging')})
        finally:
            os.chdir(previous)

    def test_inputs_resolve_from_spec_directory_and_only_runtime_assets_are_bundled(self):
        self.execute_spec()
        args, kwargs = self.analysis.call_args
        self.assertEqual(args[0], [str(self.root / 'src/retrocheevos/main.py')])
        self.assertEqual(kwargs['pathex'], [str(self.root / 'src')])
        self.assertEqual(kwargs['datas'], [
            (str(self.root / 'assets/icon.png'), 'assets'),
            (str(self.root / 'assets/logo.png'), 'assets'),
            (str(self.root / 'assets/icons'), 'assets/icons'),
            (str(self.root / 'assets/fonts'), 'assets/fonts'),
        ])
        self.assertEqual(kwargs['binaries'], [])

    def test_native_helper_and_notices_ship_together_in_new_directory(self):
        self.binary.touch()
        for name in ('RAHasher-COPYING.txt', 'RAHasher-SOURCE.txt'):
            (self.helper / name).touch()
        self.execute_spec()
        kwargs = self.analysis.call_args.kwargs
        self.assertEqual(kwargs['binaries'], [(str(self.binary), 'tools/rahasher')])
        self.assertEqual(kwargs['datas'][4:], [
            (str(self.helper / name), 'tools/rahasher')
            for name in ('RAHasher-COPYING.txt', 'RAHasher-SOURCE.txt')
        ])

    def test_missing_helper_notice_still_prevents_packaging(self):
        self.binary.touch()
        with self.assertRaises(SystemExit):
            self.execute_spec()
        self.analysis.assert_not_called()
