"""Single-file `.zip` inspection/extraction for Watch Folder scanning
(Architecture.md — Library layer).

Many ROMs (especially GBA/SNES/NES) are distributed as a `.zip` containing
exactly one file. RA's own hasher treats any `.zip` as an Arcade ROM set
(see `console_catalog.py`'s `"zip"` entry) — this module lets Watch Folder
detection look inside first, so a genuine single-ROM zip can be identified
by its *inner* file's extension instead. Real multi-file arcade sets are
untouched: they simply don't have exactly one entry, so `find_single_rom_member`
returns `None` for them and the caller falls back to the existing behavior.
"""

import logging
import shutil
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Safety cap against spoofed/zip-bomb metadata: a zip entry's declared
# uncompressed size is attacker/corruption-controlled and can lie. No real
# ROM (even an uncompressed PSP/PS2 disc image) should exceed this, so treat
# anything bigger as "don't trust it, don't extract it".
MAX_EXTRACTED_SIZE_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB


def find_single_rom_member(zip_path: Path) -> Optional[str]:
    """The member name if `zip_path` contains exactly one non-directory
    entry within the size cap, else `None`. Never raises: a corrupted,
    encrypted, or otherwise unreadable zip just means "no single member".
    """
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if len(members) != 1:
                return None

            member = members[0]
            if member.file_size > MAX_EXTRACTED_SIZE_BYTES:
                logger.warning(
                    "Skipping oversized single-file zip %s (%s claims %d bytes uncompressed)",
                    zip_path,
                    member.filename,
                    member.file_size,
                )
                return None

            return member.filename
    except (zipfile.BadZipFile, RuntimeError, OSError):
        logger.warning("Could not inspect zip %s", zip_path, exc_info=True)
        return None


def extract_member(zip_path: Path, member_name: str, destination_dir: Path) -> Path:
    """Extracts `member_name` from `zip_path` into `destination_dir`, using
    only its base filename — flattens any internal folder structure the zip
    entry's path might have (`ZipFile.extract` would otherwise recreate it).
    Returns the extracted file's path.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = destination_dir / Path(member_name).name

    with zipfile.ZipFile(zip_path) as archive, archive.open(member_name) as source:
        with open(extracted_path, "wb") as target:
            shutil.copyfileobj(source, target)

    return extracted_path
