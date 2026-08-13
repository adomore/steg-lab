"""Lab 05 -- ZIP structure: three places the format leaves room.

  (a) pseudo-encryption -- flip the "encrypted" general-purpose flag bit
      without encrypting anything. Every GUI archiver prompts for a password
      it will never verify, and analysts move on. The data was never
      protected; it was only labelled.
  (b) archive comment   -- up to 65535 bytes after the end-of-central-directory
      record. Structurally legal, never displayed by default.
  (c) inter-entry gap   -- bytes between the last local entry and the central
      directory. No structure references them, so no reader ever reads them.

All three exploit the same property: ZIP is read from the central directory
backwards, so anything the central directory declines to mention is
invisible by design. The detector therefore does the opposite -- it walks
local headers forwards and reconciles the two views.

Domain    : container
Algorithm : pseudo-encryption / comment / unreferenced-gap
"""

from __future__ import annotations

import io
import struct
import sys
import zipfile
import zlib
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.container import classify_blob, parse_zip
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "zip_structure"
DOMAIN = "container"
ALGORITHM = "pseudo-encryption/comment/unreferenced-gap"


def make_archive(entries: Optional[List[Tuple[str, bytes]]] = None) -> bytes:
    entries = entries or [
        ("readme.txt", b"nothing to see here\n"),
        ("data.bin", bytes(range(256)) * 4),
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in entries:
            zf.writestr(name, body)
    return buf.getvalue()


def embed_pseudo_encryption(archive: bytes) -> bytes:
    """Set GP flag bit 0 in every local and central header. Encrypt nothing."""
    out = bytearray(archive)

    pos = 0
    while True:
        pos = out.find(b"PK\x03\x04", pos)
        if pos == -1 or pos + 30 > len(out):
            break
        (flags,) = struct.unpack("<H", out[pos + 6:pos + 8])
        struct.pack_into("<H", out, pos + 6, flags | 0x0001)
        (csize,) = struct.unpack("<I", out[pos + 18:pos + 22])
        nlen, elen = struct.unpack("<HH", out[pos + 26:pos + 30])
        pos = pos + 30 + nlen + elen + csize

    pos = 0
    while True:
        pos = out.find(b"PK\x01\x02", pos)
        if pos == -1 or pos + 46 > len(out):
            break
        (flags,) = struct.unpack("<H", out[pos + 8:pos + 10])
        struct.pack_into("<H", out, pos + 8, flags | 0x0001)
        nlen, elen, clen = struct.unpack("<HHH", out[pos + 28:pos + 34])
        pos += 46 + nlen + elen + clen

    return bytes(out)


def embed_comment(archive: bytes, payload: bytes) -> bytes:
    eocd = archive.rfind(b"PK\x05\x06")
    if eocd == -1:
        raise ValueError("no end-of-central-directory record")
    head = bytearray(archive[:eocd + 22])
    struct.pack_into("<H", head, eocd + 20, len(payload))
    return bytes(head) + payload


def embed_gap(archive: bytes, payload: bytes) -> bytes:
    """Insert unreferenced bytes before the central directory.

    The central directory's own offset field must be advanced, otherwise
    readers reject the archive -- and an archive that does not open is not
    a hiding place, it is a broken file.
    """
    view = parse_zip(archive)
    if not view.central:
        raise ValueError("no central directory")
    cd_start = view.central[0].offset
    out = bytearray(archive[:cd_start] + payload + archive[cd_start:])

    eocd = out.rfind(b"PK\x05\x06")
    (cd_off,) = struct.unpack("<I", out[eocd + 16:eocd + 20])
    struct.pack_into("<I", out, eocd + 16, cd_off + len(payload))
    return bytes(out)


def embed(archive: bytes, payload: bytes, variant: str = "comment") -> bytes:
    if variant == "pseudo_encryption":
        return embed_pseudo_encryption(archive)
    if variant == "comment":
        return embed_comment(archive, payload)
    if variant == "gap":
        return embed_gap(archive, payload)
    raise ValueError(f"unknown variant {variant}")


def _decompresses_without_key(data: bytes, entry) -> bool:
    """Can the entry's bytes be inflated as-is? If yes, it is not encrypted."""
    blob = data[entry.data_offset:entry.data_offset + entry.comp_size]
    if not blob:
        return False
    try:
        if entry.method == 0:
            return True
        zlib.decompressobj(-15).decompress(blob)
        return True
    except zlib.error:
        return False


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    report = Report(carrier=name)
    view = parse_zip(data)

    if not view.local and view.eocd_offset in (None, -1):
        return report

    # (a) claims encryption, is not encrypted
    for entry in view.local:
        if entry.encrypted_flag and _decompresses_without_key(data, entry):
            level = cap_without_baseline(Evidence.E3, baseline)
            report.add(Finding(
                carrier=name, level=level, detector="zip_pseudo_encryption",
                claim=(f"entry '{entry.name}' sets the encrypted flag but its "
                       f"stored bytes decompress without a key"),
                domain=DOMAIN if level >= Evidence.E3 else None,
                algorithm="pseudo-encryption" if level >= Evidence.E3 else None,
                payload_offset=entry.offset + 6,
                baseline=baseline,
                detail={"method": entry.method, "flags": hex(entry.flags),
                        "comp_size": entry.comp_size},
            ))

    # local vs central disagreement about encryption
    central_by_name = {c.name: c for c in view.central}
    for entry in view.local:
        c = central_by_name.get(entry.name)
        if c is not None and c.encrypted_flag != entry.encrypted_flag:
            report.add(Finding(
                carrier=name, level=Evidence.E1, detector="zip_header_disagreement",
                claim=(f"entry '{entry.name}': local header and central directory "
                       f"disagree about the encryption flag"),
                detail={"local_flags": hex(entry.flags), "central_flags": hex(c.flags)},
            ))

    # (b) archive comment
    if view.archive_comment:
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="zip_archive_comment",
            claim=f"archive comment carries {len(view.archive_comment)} bytes",
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="archive-comment" if level >= Evidence.E3 else None,
            payload=view.archive_comment if level >= Evidence.E4 else None,
            payload_offset=(view.eocd_offset + 22) if view.eocd_offset else None,
            baseline=baseline,
            detail={"classification": classify_blob(view.archive_comment)},
        ))

    # (c) bytes no structure claims
    for offset, length in view.gaps:
        blob = data[offset:offset + length]
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="zip_unreferenced_gap",
            claim=(f"{length} bytes at offset {offset} are referenced by no "
                   f"local header, central entry or EOCD record"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="unreferenced-gap" if level >= Evidence.E3 else None,
            payload=blob if level >= Evidence.E4 else None,
            payload_offset=offset,
            baseline=baseline,
            detail={"classification": classify_blob(blob)},
        ))

    return report


def build_sample(payload: bytes, variant: str = "comment") -> bytes:
    return embed(make_archive(), payload, variant=variant)
