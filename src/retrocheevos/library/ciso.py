"""CISO (`.cso`) disc image reading (Architecture.md — Library layer).

A `.cso` is an ISO with every 2 KiB sector deflated independently, which is
why the app could see one of these sitting next to three `.iso` files and
recognize only the three: `psp_hash` parses an ISO9660 filesystem, and there
is no filesystem visible in a CISO until the blocks are inflated.

Rather than decompress ~1.2 GB to a scratch file just to read two entries out
of it, `CisoReader` presents the *decompressed* image as an ordinary seekable
binary stream and inflates only the blocks that are actually read. The disc
parser then works on it unchanged — `psp_hash` never learns that the file was
compressed, and the hash is identical to the one the equivalent `.iso` would
produce, which is the whole point: RetroAchievements has no separate hash for
a CSO, it has the hash of the disc inside it.

Format (CISO v1, the only one in the wild for PSP, and what every common
tool — CISO, maxcso, UMDGen — writes):

    offset 0    magic "CISO"
    offset 4    header size (u32; 0 from some writers, meaning 24)
    offset 8    total decompressed size (u64)
    offset 16   block size (u32; 2048 for PSP)
    offset 20   version (u8)
    offset 21   index shift (u8)
    offset 24   index: (block_count + 1) u32 entries

Each index entry holds a block's start offset in the compressed file, shifted
right by `index shift`, with the top bit set when the block was stored
uncompressed (already-random data deflates to more than 2048 bytes, so the
writer keeps it verbatim). A block's compressed length is the gap to the next
entry, which is why the index carries one extra terminating entry.

Not handled: `.zso` (same layout, LZ4 instead of deflate) and `.dax` (a
different container entirely). Both would need a new decompressor here and a
new dependency; neither is common for PSP.
"""

import io
import logging
import struct
import zlib
from pathlib import Path
from typing import BinaryIO, Optional

logger = logging.getLogger(__name__)

MAGIC = b"CISO"
_HEADER_STRUCT = struct.Struct("<4sIQIBB2x")
_DEFAULT_HEADER_SIZE = _HEADER_STRUCT.size  # 24
_PLAIN_BLOCK_FLAG = 0x80000000
_OFFSET_MASK = 0x7FFFFFFF
# A sane ceiling on the index: a 4 GiB image at the smallest plausible block
# size is well under this, and it stops a corrupt header asking for a
# multi-gigabyte allocation before anything has been validated.
_MAX_BLOCKS = 8 * 1024 * 1024


class CisoError(Exception):
    """The file isn't a CISO image this module can read."""


def is_ciso(file_path: Path) -> bool:
    """True if `file_path` starts with the CISO magic. Never raises — an
    unreadable file is simply not a CISO as far as callers are concerned.
    """
    try:
        with open(file_path, "rb") as candidate:
            return candidate.read(4) == MAGIC
    except OSError:
        return False


class CisoReader(io.RawIOBase):
    """Seekable read-only stream over a CISO's decompressed contents.

    Blocks are inflated on demand and the most recent one is kept, which is
    all the caching this needs: `psp_hash` reads a handful of scattered
    sectors to walk the directory tree, then streams two files sequentially,
    and sequential reads inside one block are the only repeat access.
    """

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self._file: Optional[BinaryIO] = open(file_path, "rb")
        try:
            self._read_header(file_path)
        except Exception:
            self._file.close()
            self._file = None
            raise
        self._position = 0
        self._cached_block_index = -1
        self._cached_block = b""

    def _read_header(self, file_path: Path) -> None:
        assert self._file is not None
        header = self._file.read(_DEFAULT_HEADER_SIZE)
        if len(header) < _DEFAULT_HEADER_SIZE:
            raise CisoError(f"Truncated CISO header: {file_path}")

        magic, header_size, total_bytes, block_size, version, index_shift = (
            _HEADER_STRUCT.unpack(header)
        )
        if magic != MAGIC:
            raise CisoError(f"Not a CISO image (bad magic): {file_path}")
        if block_size == 0:
            raise CisoError(f"CISO declares a zero block size: {file_path}")

        # Writers disagree on whether `header_size` is filled in; 0 is common
        # and means "the standard 24 bytes". Anything smaller than that would
        # put the index inside the header, so treat it the same way.
        index_offset = header_size if header_size >= _DEFAULT_HEADER_SIZE else _DEFAULT_HEADER_SIZE

        block_count = -(-total_bytes // block_size)  # ceil division
        if block_count > _MAX_BLOCKS:
            raise CisoError(
                f"CISO index implausibly large ({block_count} blocks): {file_path}"
            )

        self._file.seek(index_offset)
        raw_index = self._file.read((block_count + 1) * 4)
        if len(raw_index) < (block_count + 1) * 4:
            raise CisoError(f"Truncated CISO block index: {file_path}")

        self._index = struct.unpack(f"<{block_count + 1}I", raw_index)
        self._total_bytes = total_bytes
        self._block_size = block_size
        self._index_shift = index_shift
        self._version = version
        self._path = file_path

    # -- stream protocol -------------------------------------------------

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            new_position = offset
        elif whence == io.SEEK_CUR:
            new_position = self._position + offset
        elif whence == io.SEEK_END:
            new_position = self._total_bytes + offset
        else:
            raise ValueError(f"Invalid whence: {whence}")
        # Seeking past the end is legal and reads there return b"" — same as
        # a real file, which is what `psp_hash`'s end-of-image checks expect.
        self._position = max(0, new_position)
        return self._position

    def tell(self) -> int:
        return self._position

    def readinto(self, buffer) -> int:  # type: ignore[no-untyped-def]
        wanted = len(buffer)
        if wanted == 0 or self._position >= self._total_bytes:
            return 0

        written = 0
        remaining = min(wanted, self._total_bytes - self._position)
        while remaining > 0:
            block_index, offset_in_block = divmod(self._position, self._block_size)
            block = self._block(block_index)
            chunk = block[offset_in_block : offset_in_block + remaining]
            if not chunk:
                break  # short final block — nothing more to give
            buffer[written : written + len(chunk)] = chunk
            written += len(chunk)
            remaining -= len(chunk)
            self._position += len(chunk)
        return written

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        super().close()

    # -- block access ----------------------------------------------------

    def _block(self, block_index: int) -> bytes:
        if block_index == self._cached_block_index:
            return self._cached_block
        block = self._read_block(block_index)
        self._cached_block_index = block_index
        self._cached_block = block
        return block

    def _read_block(self, block_index: int) -> bytes:
        assert self._file is not None
        if block_index + 1 >= len(self._index):
            raise CisoError(f"Block {block_index} is past the end of {self._path}")

        entry = self._index[block_index]
        start = (entry & _OFFSET_MASK) << self._index_shift
        end = (self._index[block_index + 1] & _OFFSET_MASK) << self._index_shift
        is_plain = bool(entry & _PLAIN_BLOCK_FLAG)

        self._file.seek(start)
        if is_plain:
            return self._file.read(self._block_size)

        # Every index entry is an offset shifted right by `index_shift`, so a
        # non-zero shift rounds each one *down* to its alignment boundary. The
        # gap between two rounded offsets can therefore come out up to one
        # boundary short of the block's real compressed length — enough to cut
        # the deflate stream off mid-symbol. Reading the slack back covers it;
        # the surplus is trailing bytes the decompressor stops before.
        length = max(0, end - start)
        if self._index_shift:
            length += 1 << self._index_shift
        compressed = self._file.read(length)
        try:
            # Raw deflate: CISO stores the deflate payload with no zlib
            # wrapper, hence the negative window size. `decompressobj` rather
            # than `decompress` because only the former tolerates those extra
            # bytes instead of calling them a corrupt stream.
            return zlib.decompressobj(-zlib.MAX_WBITS).decompress(
                compressed, self._block_size
            )
        except zlib.error as error:
            raise CisoError(
                f"Block {block_index} of {self._path} failed to inflate: {error}"
            ) from error
