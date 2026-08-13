"""Lab 01 -- data appended after the structural end of the file.

The oldest trick in the box, and still the most common one in the wild,
because every mainstream decoder cooperates with it: PNG stops at IEND,
JPEG stops at EOI, GIF stops at 0x3B, and none of them care what follows.
`cat cover.png payload.zip > out.png` is a working carrier.

The detection is not clever, and that is the lesson. What makes it reliable
is not an algorithm but an accounting discipline: parse the container,
compute where it ends, compare against the file length, and treat every
unexplained byte as something that needs a name. Detectors that reason
about pixels never see this at all.

Domain    : container
Algorithm : append-after-terminator
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis import jpeg as jpeg_mod
from steganalysis import png as png_mod
from steganalysis.container import classify_blob, shannon_entropy
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "trailing_data"
DOMAIN = "container"
ALGORITHM = "append-after-terminator"

GIF_TRAILER = b"\x3b"


def structural_end(data: bytes) -> Optional[int]:
    """First byte offset that the container does not account for."""
    if data.startswith(png_mod.PNG_MAGIC):
        return png_mod.parse_png(data).iend_end
    if data[:3] == b"\xff\xd8\xff":
        return jpeg_mod.parse_jpeg(data).eoi_end
    if data[:6] in (b"GIF87a", b"GIF89a"):
        idx = data.rfind(GIF_TRAILER)
        return idx + 1 if idx != -1 else None
    return None


def embed(cover: bytes, payload: bytes) -> bytes:
    """Append the payload past the container terminator."""
    end = structural_end(cover)
    if end is None:
        raise ValueError("unrecognised container; cannot locate the terminator")
    return cover[:end] + payload


def extract(data: bytes) -> bytes:
    end = structural_end(data)
    return b"" if end is None else data[end:]


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    report = Report(carrier=name)
    end = structural_end(data)

    if end is None:
        # Inapplicability, not a finding. This lab accounts for bytes in
        # containers whose end it can compute; handed a RIFF file or a disk
        # image it has nothing to say, and saying nothing is the correct
        # output. Reporting E1 here made the pipeline flag every clean WAV and
        # AVI the moment those carriers were routed through it.
        return report

    trailing = data[end:]
    if not trailing:
        return report

    kind = classify_blob(trailing)
    entropy = shannon_entropy(trailing)

    # Payload in hand -> E4. Domain is unambiguous because the bytes sit
    # outside the container by construction, not by inference.
    level = cap_without_baseline(Evidence.E4, baseline)
    report.add(Finding(
        carrier=name,
        level=level,
        detector="trailing_data",
        claim=(f"{len(trailing)} bytes present after the container terminator "
               f"at offset {end} (classified as {kind})"),
        domain=DOMAIN if level >= Evidence.E3 else None,
        algorithm=ALGORITHM if level >= Evidence.E3 else None,
        payload=trailing if level >= Evidence.E4 else None,
        payload_offset=end,
        baseline=baseline,
        detail={"entropy_bits_per_byte": round(entropy, 3),
                "classification": kind,
                "file_size": len(data)},
    ))
    return report


def build_sample(cover: bytes, payload: bytes) -> bytes:
    return embed(cover, payload)
