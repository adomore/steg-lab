"""Lab 04 -- PNG chunk anomalies, and the one that hides pixels in plain sight.

Three variants, deliberately chosen because they fail for three different
reasons and so need three different checks:

  (a) private chunk    -- a well-formed chunk with a type nobody registered.
                          Structurally perfect; detected only by asking what
                          each chunk is *for*.
  (b) stale CRC        -- payload written over existing chunk data. Detected
                          by recomputing the CRC, which no viewer does.
  (c) height truncation -- IHDR declares fewer rows than the IDAT stream
                          actually contains. Every viewer renders the
                          declared image and silently discards the rest.
                          Detected by inflating IDAT and comparing its length
                          against what the header implies.

(c) is the one worth internalising. Nothing is hidden, nothing is appended,
every CRC is valid, and the file is a completely legal PNG. The payload is
concealed by a *declaration*, not by an encoding -- which is why entropy
scanners, appended-data checks and pixel statistics all miss it.

Domain    : container
Algorithm : private-chunk / stale-crc / header-truncation
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from PIL import Image

from steganalysis import png as png_mod
from steganalysis.container import classify_blob
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "png_chunks"
DOMAIN = "container"
ALGORITHM = "private-chunk/stale-crc/header-truncation"


def _chunk(ctype: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + ctype + body
            + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))


def embed_private_chunk(cover: bytes, payload: bytes, ctype: bytes = b"stEG") -> bytes:
    parsed = png_mod.parse_png(cover)
    iend = parsed.chunks[-1]
    return cover[:iend.offset] + _chunk(ctype, payload) + cover[iend.offset:]


def embed_stale_crc(cover: bytes, payload: bytes) -> bytes:
    """Overwrite the tail of the last IDAT without fixing its CRC."""
    parsed = png_mod.parse_png(cover)
    idats = parsed.chunks_of("IDAT")
    if not idats:
        raise ValueError("no IDAT chunk to overwrite")
    target = idats[-1]
    if len(payload) > target.length:
        raise ValueError("payload larger than the target chunk")
    data_start = target.offset + 8
    write_at = data_start + target.length - len(payload)
    out = bytearray(cover)
    out[write_at:write_at + len(payload)] = payload
    return bytes(out)


def embed_height_truncation(cover: bytes, hidden_rows: int = 40) -> bytes:
    """Re-encode with extra rows, then shrink the declared height.

    The extra rows carry a visible marker so that a successful recovery is
    self-evident when the analyst restores the true height.
    """
    img = np.array(Image.open(__import__("io").BytesIO(cover)).convert("RGB"))
    h, w, _ = img.shape
    banner = np.zeros((hidden_rows, w, 3), dtype=np.uint8)
    rng = np.random.default_rng(4242)
    banner[:, :, 0] = 220
    banner[:, :, 1] = (np.arange(w)[None, :] % 256).astype(np.uint8)
    banner[:, :, 2] = rng.integers(0, 256, (hidden_rows, w), dtype=np.uint8)
    tall = np.vstack([img, banner])

    buf = __import__("io").BytesIO()
    Image.fromarray(tall, mode="RGB").save(buf, format="PNG", compress_level=6,
                                           optimize=False)
    full = buf.getvalue()

    parsed = png_mod.parse_png(full)
    ihdr = parsed.chunks_of("IHDR")[0]
    body = bytearray(ihdr.data)
    struct.pack_into(">I", body, 4, h)          # declare the ORIGINAL height
    patched = _chunk(b"IHDR", bytes(body))       # CRC recomputed -> stays valid
    return full[:ihdr.offset] + patched + full[ihdr.offset + ihdr.total_size:]


def embed(cover: bytes, payload: bytes, variant: str = "private_chunk") -> bytes:
    if variant == "private_chunk":
        return embed_private_chunk(cover, payload)
    if variant == "stale_crc":
        return embed_stale_crc(cover, payload)
    if variant == "height_truncation":
        return embed_height_truncation(cover)
    raise ValueError(f"unknown variant {variant}")


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    report = Report(carrier=name)
    parsed = png_mod.parse_png(data)

    if not parsed.chunks:
        return report

    # (a) chunks nobody registered
    for chunk in parsed.unknown_chunks():
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="png_unknown_chunk",
            claim=(f"chunk type '{chunk.ctype}' at offset {chunk.offset} is not in "
                   f"the PNG specification "
                   f"({'private' if chunk.is_private else 'registered-space'}, "
                   f"{'ancillary' if chunk.is_ancillary else 'critical'})"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="private-chunk" if level >= Evidence.E3 else None,
            payload=chunk.data if level >= Evidence.E4 else None,
            payload_offset=chunk.offset,
            baseline=baseline,
            detail={"length": chunk.length,
                    "reserved_bit_ok": chunk.reserved_bit_ok,
                    "safe_to_copy": chunk.is_safe_to_copy,
                    "classification": classify_blob(chunk.data)},
        ))

    # (b) CRCs that no longer match their data
    for chunk in parsed.bad_crc_chunks():
        level = cap_without_baseline(Evidence.E2, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="png_crc_mismatch",
            claim=(f"chunk '{chunk.ctype}' at offset {chunk.offset} has CRC "
                   f"0x{chunk.crc_stored:08x} but its data hashes to "
                   f"0x{chunk.crc_computed:08x}"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            payload_offset=chunk.offset + 8,
            baseline=baseline,
            detail={"length": chunk.length},
        ))

    # (c) more pixel data than the header admits to
    if parsed.ihdr:
        raw = png_mod.inflate_idat(parsed)
        if raw is not None:
            expected = parsed.ihdr.expected_raw_size()
            stride = parsed.ihdr.raw_scanline_bytes()
            surplus = len(raw) - expected
            true_height = parsed.ihdr.height_for_raw_size(len(raw))
            if surplus >= stride or (true_height is not None
                                     and true_height > parsed.ihdr.height):
                hidden_rows = ((true_height - parsed.ihdr.height)
                               if true_height is not None else surplus // stride)
                level = cap_without_baseline(Evidence.E4, baseline)
                report.add(Finding(
                    carrier=name, level=level, detector="png_height_truncation",
                    claim=(f"IDAT inflates to {len(raw)} bytes but IHDR "
                           f"({parsed.ihdr.width}x{parsed.ihdr.height}) accounts for "
                           f"only {expected}; {hidden_rows} undeclared scanline(s) "
                           f"are present"),
                    domain=DOMAIN if level >= Evidence.E3 else None,
                    algorithm="header-truncation" if level >= Evidence.E3 else None,
                    payload=raw[expected:] if level >= Evidence.E4 else None,
                    payload_offset=expected,
                    baseline=baseline,
                    detail={"declared_height": parsed.ihdr.height,
                            "interlaced": bool(parsed.ihdr.interlace),
                            "true_height": parsed.ihdr.height + hidden_rows,
                            "scanline_bytes": stride,
                            "surplus_bytes": surplus},
                ))

    return report


def recover_true_height(data: bytes) -> Optional[bytes]:
    """Rewrite IHDR with the height the IDAT stream actually contains.

    Works for Adam7 as well as the flat case: the seven passes gain rows at
    different heights, so the true height is found by search rather than by
    dividing (gap G-7).
    """
    parsed = png_mod.parse_png(data)
    if not parsed.ihdr:
        return None
    raw = png_mod.inflate_idat(parsed)
    if raw is None:
        return None
    true_height = parsed.ihdr.height_for_raw_size(len(raw))
    if true_height is None:
        stride = parsed.ihdr.raw_scanline_bytes()
        true_height = len(raw) // stride if parsed.ihdr.interlace == 0 else None
    if true_height is None or true_height <= parsed.ihdr.height:
        return None
    ihdr = parsed.chunks_of("IHDR")[0]
    body = bytearray(ihdr.data)
    struct.pack_into(">I", body, 4, true_height)
    patched = _chunk(b"IHDR", bytes(body))
    return data[:ihdr.offset] + patched + data[ihdr.offset + ihdr.total_size:]


def build_sample(cover: bytes, payload: bytes, variant: str = "private_chunk") -> bytes:
    return embed(cover, payload, variant=variant)
