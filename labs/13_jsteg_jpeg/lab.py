"""Lab 13 -- Jsteg in the JPEG DCT domain, and the first C-group lab.

This lab exists because gap G-14 closed. Until the entropy encoder landed,
T2 could measure Jsteg on coefficient arrays but nothing could produce an
actual stego JPEG, so the JPEG-domain detectors had nothing to detect.

Two things make this lab worth its place:

**It reaches E4, unlike labs 07 and 09.** Those confirmed existence and
stopped, because the embedding path was keyed. Jsteg writes sequentially
into every coefficient that is neither 0 nor 1, so the extraction order is
fixed by the algorithm and the payload comes straight back out. Statistical
domain, deterministic path, payload in hand.

**The fingerprint identifies the tool, not just the presence of a payload.**
Jsteg skips the values 0 and 1. So it flattens the histogram pairs it
touches -- (2,3), (4,5) and so on -- while leaving the 0/1 ratio alone.
An embedder without that skip rule flattens everything. Checking both
halves separates "something is embedded here" from "Jsteg is embedded
here", which is the difference between E3 and an E3 that names the tool.

Domain    : jpeg-dct
Algorithm : jsteg
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)
from steganalysis.jpeg_encode import coefficients_of, recode

NAME = "jsteg_jpeg"
DOMAIN = "jpeg-dct"
ALGORITHM = "jsteg"

# p-value above which a window's touched pairs look flattened. Chi-square
# reads backwards here: a high p means "too well balanced to be natural".
#
# The textbook figure is "near 1", which is wrong for this carrier and would
# have missed every payload under about 1200 bytes. The operating point is
# taken from measurement instead: over 30 clean covers the maximum window
# p-value was 0.277 (mean 0.124), so 0.40 clears the observed clean ceiling
# with margin while sitting far below the 0.5-0.99 range embedded windows
# occupy. Re-measure it for any other source; it is a property of the
# carrier, not of the algorithm.
FLATTENED_P = 0.40
CLEAN_CEILING = 0.277        # max over 30 same-source clean covers, window 1024
# The 0/1 ratio must stay close to a clean file's for the Jsteg skip rule to
# be the explanation rather than a generic LSB embedder.
SKIP_RATIO_TOLERANCE = 0.15


def _usable(flat: np.ndarray) -> np.ndarray:
    """Coefficients Jsteg may write to: magnitude strictly greater than 1.

    Magnitude, not value. Excluding only 0 and +1 lets -1 through, and
    writing a 0 bit into -1 produces 0 -- which drops that coefficient out
    of the extraction path and desynchronises every bit after it. The bug
    was in the P1 embedder too, and this lab is what surfaced it.
    """
    return np.flatnonzero(np.abs(flat) > 1)


def embed(cover: bytes, payload: bytes, component: int = 1) -> bytes:
    """Write payload bits sequentially into usable luma DCT coefficients."""
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))

    def transform(coeffs: np.ndarray) -> np.ndarray:
        flat = coeffs.reshape(-1).astype(np.int32).copy()
        idx = _usable(flat)
        if bits.size > idx.size:
            raise ValueError(f"payload needs {bits.size} coefficients, "
                             f"carrier has {idx.size}")
        target = idx[:bits.size]
        magnitude = np.abs(flat[target])
        flat[target] = np.sign(flat[target]) * ((magnitude & ~1) | bits)
        return flat.reshape(coeffs.shape)

    return recode(cover, transform=transform, component=component)


def extract(data: bytes, nbytes: int, component: int = 1) -> bytes:
    """Jsteg's path is fixed by the algorithm, so extraction needs no key."""
    coeffs = coefficients_of(data)
    if coeffs is None:
        return b""
    flat = coeffs[component].reshape(-1)
    idx = _usable(flat)
    bits = (np.abs(flat[idx[:nbytes * 8]]) & 1).astype(np.uint8)
    return np.packbits(bits).tobytes()


def _histogram(flat: np.ndarray, limit: int = 24) -> np.ndarray:
    values = np.arange(-limit, limit + 1)
    return np.array([np.count_nonzero(flat == v) for v in values], dtype=np.float64)


def touched_pair_chi_square(values: np.ndarray) -> Tuple[float, float, int]:
    """Chi-square over the value pairs Jsteg is allowed to modify.

    Pairs (2i, 2i+1) with |2i| >= 2, both signs. The pair {0, 1} is excluded
    because Jsteg never touches it -- including it would dilute the very
    signal being measured.
    """
    # Jsteg works on MAGNITUDE, so the pairs are (2,3), (4,5), ... mirrored
    # about zero: the negative partner of -2 is -3, not -1. Pairing -2 with
    # -1 puts an untouchable value into the test and destroys it, because -1
    # keeps its natural count while -2 gets flattened against nothing.
    observed = []
    expected = []
    for magnitude in range(2, 24, 2):
        for sign in (1, -1):
            a = float(np.count_nonzero(values == sign * magnitude))
            b = float(np.count_nonzero(values == sign * (magnitude + 1)))
            if a + b < 8:
                continue
            observed.append(a)
            expected.append((a + b) / 2.0)

    if len(observed) < 3:
        return 0.0, 0.0, 0
    obs = np.array(observed)
    exp = np.array(expected)
    chi2 = float(np.sum((obs - exp) ** 2 / exp))
    dof = len(obs) - 1
    return float(1.0 - stats.chi2.cdf(chi2, dof)), chi2, dof


def windowed_chi_square(flat: np.ndarray, window: int = 1024) -> Tuple[float, int, int]:
    """Slide the test along Jsteg's own writing order and localise the payload.

    A global chi-square fails on a partial payload: the untouched tail keeps
    its natural imbalance and swamps the sum. But Jsteg writes sequentially
    into usable coefficients, so walking that same sequence shows a run of
    flattened windows at the front that collapses where the payload ends.

    Returns (peak p-value, number of consecutive flattened windows,
    estimated payload bytes). This is Westfeld and Pfitzmann's attack in the
    form that made it famous -- it does not merely detect, it measures.
    """
    idx = _usable(flat)
    seq = flat[idx]
    if seq.size < window * 2:
        window = max(seq.size // 4, 256)

    peak = 0.0
    run = 0
    for start in range(0, seq.size - window + 1, window):
        p, _, _ = touched_pair_chi_square(seq[start:start + window])
        peak = max(peak, p)
        if p >= FLATTENED_P:
            run += 1
        else:
            break
    return peak, run, (run * window) // 8


def skip_pair_ratio(flat: np.ndarray) -> float:
    ones = float(np.count_nonzero(flat == 1))
    return float(np.count_nonzero(flat == 0)) / ones if ones else 0.0


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None,
           reference_skip_ratio: Optional[float] = None,
           payload_bytes: int = 0) -> Report:
    report = Report(carrier=name)
    coeffs = coefficients_of(data)
    if coeffs is None or 1 not in coeffs:
        return report

    flat = coeffs[1].reshape(-1)
    p_value, run, estimated_bytes = windowed_chi_square(flat)
    if run == 0:
        return report

    ratio = skip_pair_ratio(flat)
    skip_intact = True
    if reference_skip_ratio:
        skip_intact = abs(ratio - reference_skip_ratio) / reference_skip_ratio \
            <= SKIP_RATIO_TOLERANCE

    level = cap_without_baseline(Evidence.E3, baseline)
    payload = None
    if payload_bytes and level >= Evidence.E3:
        payload = extract(data, payload_bytes)
        if payload:
            level = Evidence.E4

    report.add(Finding(
        carrier=name, level=level, detector="jsteg_pair_chi_square",
        claim=(f"{run} consecutive windows at the front of Jsteg's writing "
               f"order show flattened coefficient pairs (peak p={p_value:.4f}), "
               f"implying roughly {estimated_bytes} bytes of payload"
               + (" while the skipped 0/1 pair is intact, which is Jsteg's "
                  "signature rather than a generic LSB embedder"
                  if skip_intact and reference_skip_ratio else "")),
        domain=DOMAIN if level >= Evidence.E3 else None,
        algorithm=ALGORITHM if level >= Evidence.E3 else None,
        payload=payload,
        baseline=baseline,
        detail={"p_value": round(p_value, 6),
                "flattened_windows": run,
                "estimated_payload_bytes": estimated_bytes,
                "zero_over_one_ratio": round(ratio, 3),
                "skip_pair_intact": skip_intact},
    ))
    return report


def build_sample(cover: bytes, payload: bytes) -> bytes:
    return embed(cover, payload)
