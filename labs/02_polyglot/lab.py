"""Lab 02 -- polyglots, or: two parsers reading one file and both being right.

A polyglot is not a hidden payload so much as a hidden *interpretation*.
The bytes are all visible; what is concealed is that a second parser, given
the same file, produces a completely different document. PNG+ZIP works
because PNG reads forwards from a magic number and ZIP reads backwards from
the end-of-central-directory record, so the two never contend for the same
bytes.

That is why "it renders as an image" proves nothing, and why an extension
allowlist is not a control. The interesting detection question is not "what
is this file?" but "how many valid answers does that question have?".

Domain    : container
Algorithm : format-polyglot
"""

from __future__ import annotations

import io
import struct
import sys
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.container import find_signatures, parse_zip
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "polyglot"
DOMAIN = "container"
ALGORITHM = "format-polyglot"


def make_zip(entries: List[Tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in entries:
            zf.writestr(name, body)
    return buf.getvalue()


def _shift_central_directory(zip_bytes: bytes, delta: int) -> bytes:
    """Rebase a ZIP's internal offsets so it stays valid after a prefix.

    A naively appended ZIP still opens in most tools, which silently repair
    the offsets and print a warning. Rebasing removes the warning, which
    matters: analysts learn to trust warnings, and a polyglot built by
    someone competent will not produce one.
    """
    out = bytearray(zip_bytes)

    pos = 0
    while True:
        pos = out.find(b"PK\x01\x02", pos)
        if pos == -1 or pos + 46 > len(out):
            break
        (local_off,) = struct.unpack("<I", out[pos + 42:pos + 46])
        struct.pack_into("<I", out, pos + 42, local_off + delta)
        nlen, elen, clen = struct.unpack("<HHH", out[pos + 28:pos + 34])
        pos += 46 + nlen + elen + clen

    eocd = out.rfind(b"PK\x05\x06")
    if eocd != -1 and eocd + 22 <= len(out):
        (cd_off,) = struct.unpack("<I", out[eocd + 16:eocd + 20])
        struct.pack_into("<I", out, eocd + 16, cd_off + delta)

    return bytes(out)


def embed(cover: bytes, payload_entries: Optional[List[Tuple[str, bytes]]] = None,
          rebase: bool = True) -> bytes:
    """Produce a cover+ZIP polyglot."""
    entries = payload_entries or [("secret.txt", b"steg-lab lab 02 polyglot payload\n")]
    zip_bytes = make_zip(entries)
    if rebase:
        zip_bytes = _shift_central_directory(zip_bytes, len(cover))
    return cover + zip_bytes


def opens_as_zip(data: bytes) -> Optional[List[str]]:
    """Return the ZIP name list if a standard reader accepts the file."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if zf.testzip() is not None:
                return None
            return zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return None


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    report = Report(carrier=name)

    # Step 1: does a second, structurally complete format live in here?
    names = opens_as_zip(data)
    view = parse_zip(data)

    if names:
        level = cap_without_baseline(Evidence.E4, baseline)
        payload = b"\n".join(n.encode() for n in names)
        report.add(Finding(
            carrier=name, level=level, detector="polyglot_zip",
            claim=(f"file is simultaneously a valid archive containing "
                   f"{len(names)} entr{'y' if len(names) == 1 else 'ies'}"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm=ALGORITHM if level >= Evidence.E3 else None,
            payload=payload if level >= Evidence.E4 else None,
            payload_offset=view.local[0].offset if view.local else None,
            baseline=baseline,
            detail={"entries": names,
                    "local_headers": len(view.local),
                    "central_entries": len(view.central)},
        ))
        return report

    # Step 2: signatures without a complete structure. Weaker, and it
    # stays weak -- compressed data contains arbitrary byte sequences, so
    # a bare signature hit is exactly the kind of thing E1 exists for.
    hits = [(off, sig) for off, sig in find_signatures(data, start=8)
            if sig in ("zip", "rar", "7z", "pdf", "elf", "sqlite", "xz", "bzip2")]
    if hits:
        report.add(Finding(
            carrier=name, level=Evidence.E1, detector="polyglot_signature_scan",
            claim=(f"{len(hits)} embedded format signature(s) found, none forming "
                   f"a complete structure"),
            detail={"hits": hits[:12]},
        ))
    return report


def build_sample(cover: bytes) -> bytes:
    return embed(cover)
