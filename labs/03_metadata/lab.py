"""Lab 03 -- metadata as a carrier.

Metadata is a designed-in, unbounded, standards-blessed place to put bytes
that no decoder validates and no viewer displays. PNG has tEXt/zTXt/iTXt,
JPEG has COM and sixteen APPn slots, and both survive most copy operations
untouched.

The detection problem here is entirely one of *baselines*, not of physics.
Every real photograph carries metadata; a camera writes kilobytes of it.
So "this file has metadata" is worth nothing, and "this file has metadata
that does not look like the metadata this source produces" is worth
everything. That distinction is why this lab measures a clean-set profile
before it says anything.

Domain    : metadata
Algorithm : text-chunk / comment-segment payload
"""

from __future__ import annotations

import base64
import struct
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis import jpeg as jpeg_mod
from steganalysis import png as png_mod
from steganalysis.container import printable_ratio, shannon_entropy
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "metadata"
DOMAIN = "metadata"
ALGORITHM = "text-chunk-or-comment-payload"

# Above this length a text field stops looking like a caption.
SUSPICIOUS_LENGTH = 128
# Base64 of arbitrary bytes lands around 6.0 bits/byte; English prose ~4.2.
SUSPICIOUS_ENTROPY = 5.0


def _png_chunk(ctype: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + ctype + body
            + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))


def embed_png(cover: bytes, payload: bytes, keyword: str = "Comment",
              compressed: bool = False) -> bytes:
    """Insert a tEXt or zTXt chunk carrying a base64 payload before IEND."""
    parsed = png_mod.parse_png(cover)
    if not parsed.chunks or parsed.chunks[-1].ctype != "IEND":
        raise ValueError("cover is not a well-formed PNG")
    iend_offset = parsed.chunks[-1].offset
    encoded = base64.b64encode(payload)
    if compressed:
        body = keyword.encode("latin-1") + b"\x00\x00" + zlib.compress(encoded)
        chunk = _png_chunk(b"zTXt", body)
    else:
        body = keyword.encode("latin-1") + b"\x00" + encoded
        chunk = _png_chunk(b"tEXt", body)
    return cover[:iend_offset] + chunk + cover[iend_offset:]


def embed_jpeg(cover: bytes, payload: bytes) -> bytes:
    """Insert a COM segment carrying a base64 payload right after SOI."""
    if cover[:2] != b"\xff\xd8":
        raise ValueError("cover is not a JPEG")
    encoded = base64.b64encode(payload)
    if len(encoded) + 2 > 0xFFFF:
        raise ValueError("payload too large for a single COM segment")
    seg = b"\xff\xfe" + struct.pack(">H", len(encoded) + 2) + encoded
    return cover[:2] + seg + cover[2:]


def embed(cover: bytes, payload: bytes, **kw) -> bytes:
    if cover.startswith(png_mod.PNG_MAGIC):
        return embed_png(cover, payload, **kw)
    return embed_jpeg(cover, payload)


def collect_fields(data: bytes) -> List[Tuple[str, str, bytes, int]]:
    """Return [(container, label, raw_value, offset)] for every metadata field."""
    fields: List[Tuple[str, str, bytes, int]] = []

    if data.startswith(png_mod.PNG_MAGIC):
        parsed = png_mod.parse_png(data)
        for chunk in parsed.chunks:
            if chunk.ctype in png_mod.TEXT_CHUNKS:
                kw, txt = png_mod.decode_text_chunk(chunk)
                fields.append((chunk.ctype, kw, txt.encode("latin-1", "replace"),
                               chunk.offset))
            elif chunk.ctype in ("iCCP", "eXIf"):
                fields.append((chunk.ctype, chunk.ctype, chunk.data, chunk.offset))
    elif data[:3] == b"\xff\xd8\xff":
        parsed = jpeg_mod.parse_jpeg(data)
        for seg in parsed.segments:
            if seg.name == "COM" or seg.name.startswith("APP"):
                if seg.name == "APP0" and seg.data[:5] == b"JFIF\x00":
                    continue  # the mandatory JFIF header is not a payload slot
                fields.append((seg.name, seg.name, seg.data, seg.offset))

    return fields


def _looks_like_base64(blob: bytes) -> Optional[bytes]:
    stripped = bytes(b for b in blob if not chr(b).isspace())
    if len(stripped) < 24 or len(stripped) % 4 != 0:
        return None
    alphabet = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    if not set(stripped) <= alphabet:
        return None
    try:
        return base64.b64decode(stripped, validate=True)
    except Exception:
        return None


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    report = Report(carrier=name)
    fields = collect_fields(data)

    for container, label, value, offset in fields:
        ent = shannon_entropy(value)
        printable = printable_ratio(value)
        decoded = _looks_like_base64(value)

        anomalous = (len(value) >= SUSPICIOUS_LENGTH
                     or ent >= SUSPICIOUS_ENTROPY
                     or decoded is not None)
        if not anomalous:
            continue

        if decoded is not None:
            level = cap_without_baseline(Evidence.E4, baseline)
            claim = (f"{container} field '{label}' at offset {offset} holds "
                     f"{len(value)} bytes that decode as base64 to "
                     f"{len(decoded)} bytes")
            payload = decoded
        else:
            level = cap_without_baseline(Evidence.E2, baseline)
            claim = (f"{container} field '{label}' at offset {offset} is "
                     f"{len(value)} bytes at {ent:.2f} bits/byte, which does "
                     f"not look like a caption")
            payload = None

        report.add(Finding(
            carrier=name, level=level, detector="metadata_profile",
            claim=claim,
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm=ALGORITHM if level >= Evidence.E3 else None,
            payload=payload if level >= Evidence.E4 else None,
            payload_offset=offset,
            baseline=baseline,
            detail={"entropy_bits_per_byte": round(ent, 3),
                    "printable_ratio": round(printable, 3),
                    "length": len(value)},
        ))

    return report


def profile_clean(specs_data: List[bytes]) -> Dict[str, float]:
    """Summarise what metadata the clean source normally carries."""
    counts = [len(collect_fields(d)) for d in specs_data]
    lengths = [len(v) for d in specs_data for *_x, v, _o in
               [(c, l, v, o) for c, l, v, o in collect_fields(d)]]
    return {
        "mean_fields": sum(counts) / len(counts) if counts else 0.0,
        "max_fields": max(counts) if counts else 0,
        "max_field_length": max(lengths) if lengths else 0,
    }


def build_sample(cover: bytes, payload: bytes) -> bytes:
    return embed(cover, payload)
