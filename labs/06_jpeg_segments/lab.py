"""Lab 06 -- JPEG segment space, and the byte-accounting check that closes it.

JPEG gives an embedder sixteen APPn slots and an unlimited number of COM
segments, all of which decoders skip by design. Three variants here:

  (a) COM segment       -- the documented comment slot.
  (b) unusual APPn      -- a marker in a slot no normal encoder uses, often
                           carrying a fake vendor signature to look routine.
  (c) post-scan padding -- bytes between the end of the entropy-coded scan
                           and the EOI marker.

(c) is the reason this lab reimplements the scan walk rather than searching
for 0xFFD9. Compressed data contains 0xFFD9 pairs regularly; the only way to
find the *real* end of the scan is to honour byte stuffing (0xFF00) and the
restart markers. Search for the marker naively and you will "find" an EOI
inside the image data and conclude the file is truncated.

Byte accounting -- every byte belongs to a segment, to a scan, or to a
finding -- closes (a) and (b), but NOT (c). A scan has no declared length;
it ends where the next marker begins. Append bytes containing no 0xFF and
the scan walk absorbs them silently. Closing (c) requires decoding the
entropy stream and asking where the last MCU actually finished. That is why
this lab depends on steganalysis.jpeg.decode_scan, and it is the first
place in the course where structure alone runs out.

Domain    : container
Algorithm : comment-segment / rogue-appn / post-scan-padding
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis import jpeg as jpeg_mod
from steganalysis.container import classify_blob, shannon_entropy
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "jpeg_segments"
DOMAIN = "container"
ALGORITHM = "comment-segment/rogue-appn/post-scan-padding"

# APP slots a mainstream encoder actually emits: APP0 (JFIF), APP1 (EXIF/XMP),
# APP2 (ICC / FlashPix), APP13 (Photoshop IRB), APP14 (Adobe colour transform).
COMMON_APPN = {0, 1, 2, 13, 14}


def embed_comment(cover: bytes, payload: bytes) -> bytes:
    if len(payload) + 2 > 0xFFFF:
        raise ValueError("payload exceeds one COM segment")
    seg = b"\xff\xfe" + struct.pack(">H", len(payload) + 2) + payload
    return cover[:2] + seg + cover[2:]


def embed_rogue_appn(cover: bytes, payload: bytes, slot: int = 9,
                     signature: bytes = b"Ducky\x00") -> bytes:
    if not 0 <= slot <= 15:
        raise ValueError("APPn slot must be 0-15")
    body = signature + payload
    seg = bytes([0xFF, 0xE0 + slot]) + struct.pack(">H", len(body) + 2) + body
    return cover[:2] + seg + cover[2:]


def embed_post_scan(cover: bytes, payload: bytes) -> bytes:
    """Insert bytes between the end of the scan and EOI."""
    parsed = jpeg_mod.parse_jpeg(cover)
    if not parsed.scans or parsed.eoi_end is None:
        raise ValueError("cover has no scan or no EOI")
    scan_end = parsed.scans[-1].end
    # Payload must not contain 0xFF or a decoder would read it as a marker.
    safe = bytes(b if b != 0xFF else 0xFE for b in payload)
    return cover[:scan_end] + safe + cover[scan_end:]


def embed(cover: bytes, payload: bytes, variant: str = "comment") -> bytes:
    if variant == "comment":
        return embed_comment(cover, payload)
    if variant == "rogue_appn":
        return embed_rogue_appn(cover, payload)
    if variant == "post_scan":
        return embed_post_scan(cover, payload)
    raise ValueError(f"unknown variant {variant}")


def account_bytes(data: bytes) -> Tuple[int, List[Tuple[int, int]]]:
    """Return (accounted_bytes, [(gap_offset, gap_length)])."""
    parsed = jpeg_mod.parse_jpeg(data)
    spans: List[Tuple[int, int]] = []
    for seg in parsed.segments:
        spans.append((seg.offset, seg.offset + seg.total_size))
    for scan in parsed.scans:
        spans.append((scan.start, scan.end))
    spans.sort()

    gaps: List[Tuple[int, int]] = []
    cursor = 0
    accounted = 0
    for start, end in spans:
        if start > cursor:
            gaps.append((cursor, start - cursor))
        accounted += max(0, end - max(start, cursor))
        cursor = max(cursor, end)
    limit = parsed.eoi_end if parsed.eoi_end is not None else len(data)
    if cursor < limit:
        gaps.append((cursor, limit - cursor))
    return accounted, gaps


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    report = Report(carrier=name)
    parsed = jpeg_mod.parse_jpeg(data)
    if not parsed.segments:
        return report

    # (a) comment segments
    for seg in parsed.segments_of("COM"):
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="jpeg_comment_segment",
            claim=(f"COM segment at offset {seg.offset} carries "
                   f"{len(seg.data)} bytes"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="comment-segment" if level >= Evidence.E3 else None,
            payload=seg.data if level >= Evidence.E4 else None,
            payload_offset=seg.offset + 4,
            baseline=baseline,
            detail={"entropy_bits_per_byte": round(shannon_entropy(seg.data), 3),
                    "classification": classify_blob(seg.data)},
        ))

    # (b) APPn slots normal encoders do not use
    for seg in parsed.segments:
        if not seg.name.startswith("APP"):
            continue
        slot = seg.marker - 0xE0
        if slot in COMMON_APPN:
            continue
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="jpeg_rogue_appn",
            claim=(f"APP{slot} segment at offset {seg.offset} carries "
                   f"{len(seg.data)} bytes; mainstream encoders emit only "
                   f"APP{{0,1,2,13,14}}"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="rogue-appn" if level >= Evidence.E3 else None,
            payload=seg.data if level >= Evidence.E4 else None,
            payload_offset=seg.offset + 4,
            baseline=baseline,
            detail={"slot": slot,
                    "leading_bytes": seg.data[:12].hex(),
                    "classification": classify_blob(seg.data)},
        ))

    # (c1) surplus bytes inside the scan, found by decoding it
    decoded = jpeg_mod.decode_scan(parsed)
    if decoded.supported and decoded.surplus and decoded.surplus > 0:
        blob = data[decoded.consumed_end:decoded.physical_end]
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="jpeg_scan_surplus",
            claim=(f"the entropy-coded scan decodes {decoded.mcus_decoded} MCUs "
                   f"and ends at offset {decoded.consumed_end}, but the scan "
                   f"physically runs to {decoded.physical_end}: "
                   f"{decoded.surplus} surplus byte(s)"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="post-scan-padding" if level >= Evidence.E3 else None,
            payload=blob if level >= Evidence.E4 else None,
            payload_offset=decoded.consumed_end,
            baseline=baseline,
            detail={"mcus_decoded": decoded.mcus_decoded,
                    "mcus_expected": decoded.mcus_expected,
                    "classification": classify_blob(blob),
                    "entropy_bits_per_byte": round(shannon_entropy(blob), 3)},
        ))
    elif not decoded.supported:
        report.add(Finding(
            carrier=name, level=Evidence.E1, detector="jpeg_scan_surplus",
            claim=f"scan not decodable by this lab: {decoded.reason}",
            detail={"reason": decoded.reason},
        ))

    # (c2) bytes belonging to no segment and no scan
    _accounted, gaps = account_bytes(data)
    for offset, length in gaps:
        blob = data[offset:offset + length]
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="jpeg_byte_accounting",
            claim=(f"{length} bytes at offset {offset} belong to no marker "
                   f"segment and no entropy-coded scan"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="post-scan-padding" if level >= Evidence.E3 else None,
            payload=blob if level >= Evidence.E4 else None,
            payload_offset=offset,
            baseline=baseline,
            detail={"classification": classify_blob(blob),
                    "entropy_bits_per_byte": round(shannon_entropy(blob), 3)},
        ))

    return report


def segment_profile(data: bytes) -> Dict[str, int]:
    parsed = jpeg_mod.parse_jpeg(data)
    profile: Dict[str, int] = {}
    for seg in parsed.segments:
        profile[seg.name] = profile.get(seg.name, 0) + 1
    return profile


def build_sample(cover: bytes, payload: bytes, variant: str = "comment") -> bytes:
    return embed(cover, payload, variant=variant)
