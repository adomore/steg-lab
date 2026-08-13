"""Lab 10 -- palette carriers, and hiding in an ordering rather than in a value.

A palette image stores indices, not colours. That gives an embedder two places
to work and only one of them is obvious.

**The obvious one** is the index LSB, and it does not work. Palette order is
arbitrary -- a quantiser emits colours in whatever order its algorithm reached
them -- so flipping the low bit of an index swaps a pixel for an unrelated
colour. The result is visibly wrong, which is a detector nobody needs.

**EzStego's move** is to stop treating the index as a number and start treating
it as a position in a *sorted* order. Sort the palette by luminance; now index
2k and index 2k+1 name colours that are adjacent in brightness, so flipping
between them is nearly invisible. The payload lives in the LSB of the
luminance-sorted position.

That is the whole trick, and it is also the whole tell. Sorting by luminance
turns the palette into a sequence of near-duplicate pairs, and embedding
equalises the counts within each pair -- the same structure the chi-square
attack finds in the spatial domain, applied to sorted positions rather than to
pixel values. A detector that looks at raw index statistics sees nothing; one
that sorts first sees it immediately.

Domain    : palette
Algorithm : ezstego
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "palette"
DOMAIN = "palette"
ALGORITHM = "ezstego"

#: p-value above which the sorted-index pairs look flattened. As everywhere in
#: this repository this is measured on the source, not quoted: see the lab
#: README for the clean distribution it came from.
FLATTENED_P = 0.60


def to_palette_png(data: bytes, colours: int = 64) -> bytes:
    """Quantise a carrier to a palette image, the way a GIF or PNG-8 would."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    quantised = img.quantize(colors=colours, method=Image.MEDIANCUT)
    buf = io.BytesIO()
    quantised.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _open_palette(data: bytes) -> Tuple[np.ndarray, np.ndarray]:
    """Return (indices, palette as N x 3)."""
    img = Image.open(io.BytesIO(data))
    if img.mode != "P":
        raise ValueError("not a palette image")
    indices = np.array(img)
    flat = img.getpalette() or []
    palette = np.array(flat, dtype=np.uint8).reshape(-1, 3)
    return indices, palette[: int(indices.max()) + 1]


def luminance_order(palette: np.ndarray) -> np.ndarray:
    """Palette entry indices, sorted by ITU-R 601 luma.

    This is the ordering EzStego embeds in and the ordering a detector has to
    reconstruct. It depends only on the palette, which travels with the file,
    so the analyst can rebuild it exactly.
    """
    luma = (0.299 * palette[:, 0] + 0.587 * palette[:, 1]
            + 0.114 * palette[:, 2])
    return np.argsort(luma, kind="stable")


def embed(cover: bytes, payload: bytes) -> bytes:
    """EzStego: write payload bits into the LSB of the luminance-sorted position."""
    indices, palette = _open_palette(cover)
    order = luminance_order(palette)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)          # palette index -> sorted position

    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    flat = indices.reshape(-1).copy()
    if bits.size > flat.size:
        raise ValueError(f"payload needs {bits.size} pixels, carrier has {flat.size}")

    positions = rank[flat[: bits.size]]
    positions = (positions & ~1) | bits
    positions = np.clip(positions, 0, order.size - 1)
    flat[: bits.size] = order[positions]

    out = Image.fromarray(flat.reshape(indices.shape).astype(np.uint8), mode="P")
    out.putpalette(palette.reshape(-1).tolist())
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def extract(data: bytes, nbytes: int) -> bytes:
    """No key needed: the ordering is derivable from the palette in the file."""
    indices, palette = _open_palette(data)
    order = luminance_order(palette)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    bits = (rank[indices.reshape(-1)[: nbytes * 8]] & 1).astype(np.uint8)
    return np.packbits(bits).tobytes()


def sorted_pair_chi_square(data: bytes) -> Optional[Dict[str, float]]:
    """Chi-square over pairs of luminance-adjacent palette entries.

    Run on raw indices this finds nothing, because palette order is arbitrary
    and its pairs are meaningless. Sorted first, the pairs are the ones the
    embedder actually works between.
    """
    try:
        indices, palette = _open_palette(data)
    except Exception:
        return None
    order = luminance_order(palette)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    positions = rank[indices.reshape(-1)]
    hist = np.bincount(positions, minlength=order.size).astype(np.float64)

    observed, expected = [], []
    for k in range(0, (order.size // 2) * 2, 2):
        a, b = hist[k], hist[k + 1]
        if a + b < 8:
            continue
        observed.append(a)
        expected.append((a + b) / 2.0)
    if len(observed) < 3:
        return None

    obs, exp = np.array(observed), np.array(expected)
    chi2 = float(np.sum((obs - exp) ** 2 / exp))
    dof = len(obs) - 1
    return {"p_value": float(1.0 - stats.chi2.cdf(chi2, dof)),
            "chi2": chi2, "dof": dof, "pairs": len(obs),
            "palette_entries": int(order.size)}


def windowed_chi_square(data: bytes, window: int = 4096
                        ) -> Optional[Dict[str, float]]:
    """Slide the sorted-pair test along EzStego's own writing order.

    A global test fails on a partial payload: the untouched tail keeps its
    natural imbalance and swamps the sum. Measured, a 300-byte payload in a
    192x192 carrier touches 6.5% of pixels and moves the global p-value not at
    all. EzStego writes sequentially from the first pixel, so walking that same
    order shows a run of flattened windows at the front -- the same shape lab
    13 needed for Jsteg, and the same reason.
    """
    try:
        indices, palette = _open_palette(data)
    except Exception:
        return None
    order = luminance_order(palette)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    positions = rank[indices.reshape(-1)]

    if positions.size < window * 2:
        window = max(positions.size // 4, 512)

    peak, run = 0.0, 0
    for start in range(0, positions.size - window + 1, window):
        block = positions[start:start + window]
        hist = np.bincount(block, minlength=order.size).astype(np.float64)
        observed, expected = [], []
        for k in range(0, (order.size // 2) * 2, 2):
            a, b = hist[k], hist[k + 1]
            if a + b < 8:
                continue
            observed.append(a)
            expected.append((a + b) / 2.0)
        if len(observed) < 3:
            break
        obs, exp = np.array(observed), np.array(expected)
        chi2 = float(np.sum((obs - exp) ** 2 / exp))
        p = float(1.0 - stats.chi2.cdf(chi2, len(obs) - 1))
        peak = max(peak, p)
        if p >= FLATTENED_P:
            run += 1
        else:
            break

    return {"p_value": peak, "flattened_windows": run,
            "window": window,
            "estimated_payload_bytes": (run * window) // 8,
            "palette_entries": int(order.size)}


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None,
           payload_bytes: int = 0) -> Report:
    report = Report(carrier=name)
    stat = windowed_chi_square(data)
    if stat is None or stat["flattened_windows"] == 0:
        return report

    level = cap_without_baseline(Evidence.E3, baseline)
    payload = None
    if payload_bytes and level >= Evidence.E3:
        payload = extract(data, payload_bytes)
        if payload:
            level = Evidence.E4

    report.add(Finding(
        carrier=name, level=level, detector="palette_sorted_pair_chi_square",
        claim=(f"{stat['flattened_windows']} consecutive windows at the front "
               f"of EzStego's writing order show flattened counts within "
               f"luminance-adjacent palette pairs (peak p={stat['p_value']:.4f}), "
               f"implying roughly {stat['estimated_payload_bytes']} bytes"),
        domain=DOMAIN if level >= Evidence.E3 else None,
        algorithm=ALGORITHM if level >= Evidence.E3 else None,
        payload=payload,
        baseline=baseline,
        detail={k: round(v, 5) if isinstance(v, float) else v
                for k, v in stat.items()},
    ))
    return report


def build_sample(cover: bytes, payload: bytes) -> bytes:
    return embed(to_palette_png(cover), payload)
