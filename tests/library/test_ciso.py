import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from retrocheevos.library import ciso, psp_hash
from retrocheevos.library.ciso import CisoError, CisoReader
from tests.library.test_psp_hash import _build_psp_iso


def _build_ciso(
    payload: bytes,
    block_size: int = 2048,
    header_size: int = 24,
    plain_blocks: frozenset[int] = frozenset(),
    index_shift: int = 0,
) -> bytes:
    """Compress `payload` into a CISO v1 image.

    Deliberately a writer, not a fixture: a hand-rolled byte blob would only
    prove the reader agrees with whatever the test author believed, whereas
    round-tripping real payloads through this catches the off-by-one in the
    index that the format's trailing terminator entry invites.
    """
    block_count = -(-len(payload) // block_size)
    padded = payload.ljust(block_count * block_size, b"\x00")

    body = bytearray()
    index: list[int] = []
    data_start = header_size + (block_count + 1) * 4

    for block_index in range(block_count):
        block = padded[block_index * block_size : (block_index + 1) * block_size]
        position = data_start + len(body)
        if position % (1 << index_shift):  # keep every entry exactly representable
            padding = (1 << index_shift) - (position % (1 << index_shift))
            body.extend(b"\x00" * padding)
            position += padding

        if block_index in plain_blocks:
            index.append((position >> index_shift) | 0x80000000)
            body.extend(block)
        else:
            index.append(position >> index_shift)
            compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
            body.extend(compressor.compress(block) + compressor.flush())

    end = data_start + len(body)
    index.append(end >> index_shift)

    header = struct.pack(
        "<4sIQIBB2x", b"CISO", header_size, len(payload), block_size, 1, index_shift
    )
    return header.ljust(header_size, b"\x00") + struct.pack(
        f"<{block_count + 1}I", *index
    ) + bytes(body)


class CisoReaderTests(unittest.TestCase):
    def _written(self, tmpdir: str, data: bytes, **kwargs) -> Path:
        path = Path(tmpdir) / "image.cso"
        path.write_bytes(_build_ciso(data, **kwargs))
        return path

    def test_reads_back_exactly_what_was_compressed(self) -> None:
        payload = bytes(range(256)) * 40  # 10240 bytes = 5 blocks
        with tempfile.TemporaryDirectory() as tmpdir:
            with CisoReader(self._written(tmpdir, payload)) as reader:
                self.assertEqual(reader.read(), payload)

    def test_partial_final_block_stops_at_declared_size(self) -> None:
        payload = b"x" * (2048 * 2 + 17)
        with tempfile.TemporaryDirectory() as tmpdir:
            with CisoReader(self._written(tmpdir, payload)) as reader:
                data = reader.read()
        self.assertEqual(len(data), len(payload))
        self.assertEqual(data, payload)

    def test_seek_and_read_across_a_block_boundary(self) -> None:
        payload = bytes((i * 7) % 251 for i in range(2048 * 4))
        with tempfile.TemporaryDirectory() as tmpdir:
            with CisoReader(self._written(tmpdir, payload)) as reader:
                reader.seek(2048 - 5)
                self.assertEqual(reader.read(10), payload[2043:2053])

                reader.seek(0, io.SEEK_END)
                self.assertEqual(reader.tell(), len(payload))
                self.assertEqual(reader.read(16), b"")

                reader.seek(-100, io.SEEK_END)
                self.assertEqual(reader.read(), payload[-100:])

    def test_uncompressed_blocks_are_honoured(self) -> None:
        """Incompressible data is stored verbatim with the top index bit set —
        a real image is a mix, so both paths must agree.
        """
        payload = bytes(range(256)) * 24
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._written(tmpdir, payload, plain_blocks=frozenset({0, 2}))
            with CisoReader(path) as reader:
                self.assertEqual(reader.read(), payload)

    def test_index_shift_is_applied(self) -> None:
        payload = bytes(range(256)) * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._written(tmpdir, payload, index_shift=3)
            with CisoReader(path) as reader:
                self.assertEqual(reader.read(), payload)

    def test_zero_header_size_means_the_standard_24_bytes(self) -> None:
        """Several writers leave the field at 0. Reading the index from offset
        0 instead of 24 would land inside the header and desync everything.
        """
        payload = b"pspdisc" * 900
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "image.cso"
            built = bytearray(_build_ciso(payload))
            struct.pack_into("<I", built, 4, 0)
            path.write_bytes(bytes(built))
            with CisoReader(path) as reader:
                self.assertEqual(reader.read(), payload)

    def test_rejects_a_non_ciso_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "plain.iso"
            path.write_bytes(b"CD001" * 1000)
            self.assertFalse(ciso.is_ciso(path))
            with self.assertRaises(CisoError):
                CisoReader(path)

    def test_rejects_a_truncated_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cut.cso"
            path.write_bytes(_build_ciso(b"y" * 8192)[:30])
            with self.assertRaises(CisoError):
                CisoReader(path)

    def test_is_ciso_detects_by_magic_not_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "renamed.iso"
            path.write_bytes(_build_ciso(b"z" * 4096))
            self.assertTrue(ciso.is_ciso(path))


class PspHashThroughCisoTests(unittest.TestCase):
    def test_cso_hashes_identically_to_the_iso_it_was_made_from(self) -> None:
        """The whole justification for `ciso`: RetroAchievements has no hash
        for a CSO, it has the hash of the disc inside one. If these two ever
        diverge, every `.cso` in a library silently stops matching.
        """
        iso_bytes = _build_psp_iso(b"param sfo content", b"eboot bin content")
        with tempfile.TemporaryDirectory() as tmpdir:
            iso_path = Path(tmpdir) / "game.iso"
            iso_path.write_bytes(iso_bytes)
            cso_path = Path(tmpdir) / "game.cso"
            cso_path.write_bytes(_build_ciso(iso_bytes))

            self.assertEqual(
                psp_hash.compute_psp_iso_hash(cso_path),
                psp_hash.compute_psp_iso_hash(iso_path),
            )

    def test_cso_is_recognized_as_a_psp_disc(self) -> None:
        iso_bytes = _build_psp_iso(b"param sfo content", b"eboot bin content")
        with tempfile.TemporaryDirectory() as tmpdir:
            cso_path = Path(tmpdir) / "game.cso"
            cso_path.write_bytes(_build_ciso(iso_bytes))
            self.assertTrue(psp_hash.looks_like_psp_disc(cso_path))

    def test_a_cso_that_is_not_a_psp_disc_is_reported_as_such(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cso_path = Path(tmpdir) / "notagame.cso"
            cso_path.write_bytes(_build_ciso(b"\x00" * 40960))
            self.assertFalse(psp_hash.looks_like_psp_disc(cso_path))
            with self.assertRaises(psp_hash.NotAPspDiscError):
                psp_hash.compute_psp_iso_hash(cso_path)

    def test_corrupt_cso_does_not_escape_as_a_ciso_error(self) -> None:
        """Callers catch `NotAPspDiscError`; a `CisoError` leaking through
        would abort a whole folder scan instead of skipping one file.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "broken.cso"
            built = bytearray(_build_ciso(b"q" * 8192))
            built[-40:] = b"\xff" * 40
            path.write_bytes(bytes(built))

            self.assertFalse(psp_hash.looks_like_psp_disc(path))
            with self.assertRaises(psp_hash.NotAPspDiscError):
                psp_hash.compute_psp_iso_hash(path)


if __name__ == "__main__":
    unittest.main()
