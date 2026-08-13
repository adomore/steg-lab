"""Lab 07 -- LSB replacement in the spatial domain, and the E3 ceiling.

This is the first lab whose verdict is statistical rather than structural.
Everything in the A group produced the payload; here the detectors produce a
*number*, and a number needs a threshold, and a threshold needs a baseline.
That is why the evidence ladder tops out at E3 for this lab: RS analysis and
Weighted Stego establish that a payload exists and estimate its size, but
neither yields a byte of it without the embedding path.

Recovering the payload requires knowing the spread order. When embedding is
sequential from the first sample, extraction is trivial and the finding
climbs to E4; when positions are drawn from a keyed permutation, it does
not, and the honest report says E3 with an estimated payload size.

Domain    : spatial
Algorithm : lsb-replacement
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis import detectors as D
from steganalysis import embedders as E
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "lsb_replacement"
DOMAIN = "spatial"
ALGORITHM = "lsb-replacement"

# Thresholds come from gate G4's measured operating points, not from taste.
RS_THRESHOLD = 0.344
WS_THRESHOLD = 0.376


def _to_array(data: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(data)).convert("L"))


def _to_png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8), mode="L").save(
        buf, format="PNG", compress_level=6, optimize=False)
    return buf.getvalue()


def embed(cover: bytes, payload: bytes = b"", rate: float = 0.5,
          seed: int = 0, sequential: bool = False) -> bytes:
    """Embed at a given relative payload. `sequential` disables the keyed spread."""
    arr = _to_array(cover)
    if payload:
        bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
        flat = arr.reshape(-1).copy()
        idx = (np.arange(bits.size) if sequential
               else np.random.default_rng(12345).permutation(flat.size)[:bits.size])
        flat[idx] = (flat[idx] & 0xFE) | bits
        return _to_png(flat.reshape(arr.shape))
    result = E.lsb_replacement(arr, rate, seed=seed,
                               spread_seed=None if sequential else 12345)
    return _to_png(result.stego)


def extract_sequential(data: bytes, nbytes: int) -> bytes:
    flat = _to_array(data).reshape(-1)
    bits = (flat[:nbytes * 8] & 1).astype(np.uint8)
    return np.packbits(bits).tobytes()


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    report = Report(carrier=name)
    try:
        arr = _to_array(data)
    except Exception:
        return report

    rs = D.rs_analysis(arr)
    ws = D.weighted_stego(arr)

    for est, threshold in ((rs, RS_THRESHOLD), (ws, WS_THRESHOLD)):
        if est.value < threshold:
            continue
        level = cap_without_baseline(Evidence.E3, baseline)
        report.add(Finding(
            carrier=name, level=level, detector=est.detector,
            claim=(f"estimated relative payload {est.value:.3f} bpp exceeds the "
                   f"operating threshold {threshold:.3f}"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm=ALGORITHM if level >= Evidence.E3 else None,
            baseline=baseline,
            detail={"estimate_bpp": round(est.value, 4),
                    "threshold": threshold,
                    "estimated_payload_bytes": int(est.value * arr.size / 8)},
        ))
    return report


def build_sample(cover: bytes, rate: float = 0.5) -> bytes:
    return embed(cover, rate=rate)
