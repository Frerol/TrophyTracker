import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from retrocheevos.library import hashing, rahasher
from retrocheevos.library.rahasher import RaHasherError

# A real RAHasher.exe is not in this repository (GPL-3.0, see Retrocheevos.spec),
# so these drive a stand-in that reproduces its documented contract: hash on
# stdout, exit 0; reason on stderr, exit 1. The point under test is this
# module's half of that contract — argument order, output validation, failure
# handling — none of which needs the real binary, and all of which would
# otherwise go untested on any machine that hasn't downloaded it.
_STUB = textwrap.dedent(
    """
    import sys
    console_id, file_path = sys.argv[1], sys.argv[2]
    behaviour = __import__("os").environ.get("STUB_BEHAVIOUR", "ok")
    if behaviour == "ok":
        sys.stdout.write("0123456789abcdef0123456789abcdef\\n")
    elif behaviour == "echo_args":
        sys.stdout.write(f"{console_id}|{file_path}")
    elif behaviour == "fail":
        sys.stderr.write("could not identify game\\n")
        sys.exit(1)
    elif behaviour == "garbage":
        sys.stdout.write("not a hash at all\\n")
    elif behaviour == "silent_success":
        sys.stdout.write("\\n")
    """
)


class _StubHasher:
    """Installs a fake RAHasher on PATH-independent lookup via the env override."""

    def __init__(self, tmpdir: str, behaviour: str = "ok") -> None:
        script = Path(tmpdir) / "stub_rahasher.py"
        script.write_text(_STUB, encoding="utf-8")
        launcher = Path(tmpdir) / (
            "RAHasher.cmd" if sys.platform == "win32" else "RAHasher"
        )
        if sys.platform == "win32":
            launcher.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        else:
            launcher.write_text(
                f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
            )
            launcher.chmod(0o755)
        self.path = launcher
        self.behaviour = behaviour

    def __enter__(self) -> "_StubHasher":
        self._patch = mock.patch.dict(
            os.environ,
            {rahasher.ENV_OVERRIDE: str(self.path), "STUB_BEHAVIOUR": self.behaviour},
        )
        self._patch.start()
        return self

    def __exit__(self, *exc) -> None:
        self._patch.stop()


class FindExecutableTests(unittest.TestCase):
    def test_absent_binary_is_a_supported_state(self) -> None:
        with mock.patch.dict(os.environ, {rahasher.ENV_OVERRIDE: "Z:/nope/RAHasher.exe"}):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch.object(Path, "is_file", return_value=False):
                    self.assertIsNone(rahasher.find_executable())
                    self.assertFalse(rahasher.is_available())

    def test_environment_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with _StubHasher(tmpdir) as stub:
                self.assertEqual(rahasher.find_executable(), stub.path)
                self.assertTrue(rahasher.is_available())

    def test_lookup_is_not_cached_so_a_dropped_in_binary_is_noticed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stub = _StubHasher(tmpdir)
            missing = Path(tmpdir) / "not-here-yet.exe"
            with mock.patch.dict(os.environ, {rahasher.ENV_OVERRIDE: str(missing)}):
                with mock.patch("shutil.which", return_value=None):
                    before = rahasher.find_executable()
            with mock.patch.dict(os.environ, {rahasher.ENV_OVERRIDE: str(stub.path)}):
                after = rahasher.find_executable()
            self.assertNotEqual(before, after)
            self.assertEqual(after, stub.path)


class ComputeHashTests(unittest.TestCase):
    def test_returns_the_hash_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "game.gba"
            rom.write_bytes(b"rom")
            with _StubHasher(tmpdir):
                self.assertEqual(
                    rahasher.compute_hash(rom, 5), "0123456789abcdef0123456789abcdef"
                )

    def test_passes_console_id_then_path_in_that_order(self) -> None:
        """RAHasher's argument order is `<console_id> <file>`; swapping them
        makes it try to open the id as a filename and fail on every ROM.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "Some Game (USA).chd"
            rom.write_bytes(b"disc")
            with _StubHasher(tmpdir, behaviour="echo_args"):
                with self.assertRaises(RaHasherError) as caught:
                    rahasher.compute_hash(rom, 12)
        self.assertIn("12|", str(caught.exception))
        self.assertIn("Some Game (USA).chd", str(caught.exception))

    def test_nonzero_exit_raises_with_the_stderr_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "mystery.bin"
            rom.write_bytes(b"?")
            with _StubHasher(tmpdir, behaviour="fail"):
                with self.assertRaises(RaHasherError) as caught:
                    rahasher.compute_hash(rom, 12)
        self.assertIn("could not identify game", str(caught.exception))

    def test_unparseable_output_is_refused_rather_than_stored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "game.nes"
            rom.write_bytes(b"rom")
            for behaviour in ("garbage", "silent_success"):
                with self.subTest(behaviour=behaviour):
                    with _StubHasher(tmpdir, behaviour=behaviour):
                        with self.assertRaises(RaHasherError):
                            rahasher.compute_hash(rom, 7)

    def test_missing_binary_raises_rather_than_returning_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "game.nes"
            rom.write_bytes(b"rom")
            with mock.patch.object(rahasher, "find_executable", return_value=None):
                with self.assertRaises(RaHasherError):
                    rahasher.compute_hash(rom, 7)


class HashingIntegrationTests(unittest.TestCase):
    def test_rahasher_is_preferred_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "game.gba"
            rom.write_bytes(b"rom bytes")
            with _StubHasher(tmpdir):
                self.assertEqual(
                    hashing.compute_rom_hash(rom, 5), "0123456789abcdef0123456789abcdef"
                )

    def test_falls_back_to_builtin_hashing_when_rahasher_fails(self) -> None:
        """A ROM RA has no algorithm for must not abort the scan — the
        built-in answer is no worse than before RAHasher existed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "game.gba"
            rom.write_bytes(b"rom bytes")
            with _StubHasher(tmpdir, behaviour="fail"):
                from_rahasher_path = hashing.compute_rom_hash(rom, 5)

            with mock.patch.object(rahasher, "is_available", return_value=False):
                builtin = hashing.compute_rom_hash(rom, 5)

        self.assertEqual(from_rahasher_path, builtin)

    def test_builtin_path_is_unchanged_when_rahasher_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "game.gba"
            rom.write_bytes(b"abc")
            with mock.patch.object(rahasher, "is_available", return_value=False):
                self.assertEqual(
                    hashing.compute_rom_hash(rom, 5),
                    "900150983cd24fb0d6963f7d28e17f72",  # md5(b"abc")
                )

    def test_no_console_id_never_invokes_rahasher(self) -> None:
        """RAHasher's auto-detect mode prints several concatenated hashes,
        so a call without a console must not reach it.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            rom = Path(tmpdir) / "game.bin"
            rom.write_bytes(b"abc")
            with _StubHasher(tmpdir):
                self.assertEqual(
                    hashing.compute_rom_hash(rom), "900150983cd24fb0d6963f7d28e17f72"
                )


if __name__ == "__main__":
    unittest.main()
