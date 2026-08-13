"""Lab 14 -- F5 detection by calibration, and what shrinkage gives away.

Gate G2 measured that shrinkage costs F5 45.3% of its embedding efficiency.
This lab is the other half of that finding: the same mechanism that costs the
embedder payload hands the analyst a signature.

The problem with any histogram attack on JPEG is that you do not have the
cover histogram to compare against. Calibration manufactures an estimate of
it: decompress the stego image to pixels, **crop by four pixels** so the 8x8
grid no longer lines up with the original blocks, and recompress with the
*same* quantisation table. The result is an image with almost the same content
and an almost-independent DCT decomposition -- close enough to the cover's
statistics to compare against, and no longer carrying the payload, because the
payload lived in coefficients that no longer exist.

F5 decrements coefficient magnitudes, so with beta as the change rate:

    h_stego(d) = h_cover(d) * (1 - beta) + h_cover(d + 1) * beta   for d >= 1
    h_stego(0) = h_cover(0) + h_cover(1) * beta

The first line gives a least-squares estimate of beta from the calibrated
histogram. The second is shrinkage itself: coefficients of magnitude one
decremented into zero.

**The zero-excess statistic does not name the algorithm, and an earlier
version of this module claimed it did.** Measured discrimination between F5
and its shrinkage-free variant, given only stego images: AUC 0.622 at 0.05
bpp and 0.736 at 0.15. The reason is structural rather than a tuning problem
-- the calibration reference is computed *from the stego image*, so any
embedder that alters pixels also shifts the reference, and the shrinkage
signal does not survive the subtraction. Shrinkage is real in coefficient
space; gate G2 measures it directly. Calibration does not isolate it.

What does separate the two is beta itself, at AUC 0.811 and 0.984 -- and for a
reason that follows straight from G2. Shrinkage wastes changes, so at the same
payload F5 modifies roughly twice as many coefficients as the shrinkage-free
variant: measured true change rates at 0.15 bpp are 0.099 against 0.044. The
detector is telling them apart by change rate, not by shrinkage.

That inverts the usual argument for nsF5. The textbook version is that it
removes a histogram artefact. The measured version is that it costs less
payload (G2: 45.3% of the embedding efficiency) *and* changes fewer
coefficients for the same message, which is a security gain the histogram
story never mentions.

Domain    : jpeg-dct
Algorithm : f5
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis import embedders as E
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)
from steganalysis.jpeg_encode import coefficients_of, recode

NAME = "f5_calibration"
DOMAIN = "jpeg-dct"
ALGORITHM = "f5"

#: Bins used for the least-squares fit. d=1 and d=2 carry most of the mass
#: while staying clear of bin 0, where the calibration's own bias lives.
FIT_BINS = (1, 2)

#: Default operating point, measured rather than chosen: on 24 clean
#: same-source covers beta has mean -0.152 and standard deviation 0.010, so
#: -0.13 sits about two standard deviations above the clean mean. Re-measure
#: it for any other source -- like every threshold in this repository, it is a
#: property of the carrier.
CLEAN_BETA_MEAN = -0.152
CLEAN_BETA_SD = 0.010


def to_grayscale_jpeg(data: bytes, quality: int = 85) -> bytes:
    """F5 attacks are described on luminance; grayscale removes chroma noise."""
    arr = np.array(Image.open(io.BytesIO(data)).convert("L"))
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def embed(cover: bytes, rate: float = 0.5, k: int = 3, seed: int = 0,
          no_shrinkage: bool = False) -> bytes:
    """Embed with F5 (or its shrinkage-free variant) and write a real JPEG."""
    def transform(coeffs: np.ndarray) -> np.ndarray:
        return E.f5(coeffs, rate, k=k, seed=seed,
                    no_shrinkage=no_shrinkage).stego
    return recode(cover, transform=transform, component=1)


def ac_magnitude_histogram(data: bytes, limit: int = 6) -> Optional[np.ndarray]:
    """Histogram of |AC coefficient| over 0..limit.

    DC coefficients are excluded: they are not part of F5's embedding path and
    their distribution is dominated by image content rather than by the
    quantiser, so including them adds variance and no signal.
    """
    coeffs = coefficients_of(data)
    if coeffs is None or 1 not in coeffs:
        return None
    ac = np.abs(coeffs[1][:, 1:]).reshape(-1)
    return np.array([np.count_nonzero(ac == v) for v in range(limit + 1)],
                    dtype=np.float64)


def calibrate(data: bytes, crop: int = 4) -> Optional[np.ndarray]:
    """Estimate the cover histogram by cropped recompression.

    The quantisation table must be carried across exactly. Recompressing at a
    nominal 'same quality' instead would change the table and compare two
    different quantisers, which produces a confident number about nothing.
    """
    try:
        img = Image.open(io.BytesIO(data))
        qtables = img.quantization
        arr = np.array(img.convert("L"))
    except Exception:
        return None
    if arr.shape[0] <= crop or arr.shape[1] <= crop:
        return None

    buf = io.BytesIO()
    Image.fromarray(arr[crop:, crop:], mode="L").save(
        buf, format="JPEG", qtables=qtables)
    return ac_magnitude_histogram(buf.getvalue())


def estimate_change_rate(data: bytes) -> Optional[Dict[str, float]]:
    """Least-squares beta from the calibrated histogram, plus the zero excess."""
    h_s = ac_magnitude_histogram(data)
    h_c = calibrate(data)
    if h_s is None or h_c is None:
        return None

    num = den = 0.0
    for d in FIT_BINS:
        a = h_c[d + 1] - h_c[d]
        b = h_s[d] - h_c[d]
        num += a * b
        den += a * a
    beta = num / den if den > 0 else 0.0

    # Zero excess. Reported because it is the quantity the shrinkage argument
    # is about -- but see the module docstring: it does NOT reliably name the
    # algorithm, because the calibration reference is derived from the stego
    # image and moves with it.
    zero_excess = ((h_s[0] - h_c[0]) / h_c[1]) if h_c[1] > 0 else 0.0

    return {"beta": float(beta), "zero_excess": float(zero_excess),
            "h_stego": h_s.tolist(), "h_calibrated": h_c.tolist()}


@dataclass
class SourceModel:
    """Population reference: what this source's clean carriers look like.

    Calibration estimates the reference *from the carrier under examination*,
    which is why it cannot isolate shrinkage -- any embedder that alters pixels
    also moves the reference, and the signal does not survive the subtraction
    (gap G-20, measured at AUC 0.622-0.736 for F5 against its shrinkage-free
    variant).

    A population model does not move. Build it from clean carriers of the same
    source and the same quantisation table, and the suspect is compared against
    something it had no part in producing.

    This asks for nothing the evidence ladder did not already require: E3 and
    above already need a measured false-positive baseline on same-source clean
    carriers. Those same carriers build this. The requirement was always there;
    it now does two jobs.
    """

    mean: np.ndarray
    sd: np.ndarray
    n_clean: int
    limit: int
    description: str

    def z_scores(self, data: bytes) -> Optional[np.ndarray]:
        h = ac_magnitude_histogram(data, limit=self.limit)
        if h is None or h.sum() == 0:
            return None
        return (h / h.sum() - self.mean) / self.sd


def build_source_model(clean: Sequence[bytes], limit: int = 6,
                       description: str = "same-source clean grayscale JPEGs"
                       ) -> SourceModel:
    """Normalised AC-magnitude histogram statistics over clean carriers.

    Normalised per carrier before averaging, so a large image does not outvote
    a small one, and so the model describes histogram *shape* rather than size.
    """
    rows = []
    for blob in clean:
        h = ac_magnitude_histogram(blob, limit=limit)
        if h is not None and h.sum() > 0:
            rows.append(h / h.sum())
    if len(rows) < 4:
        raise ValueError(f"need at least 4 usable clean carriers, got {len(rows)}")
    stack = np.array(rows)
    return SourceModel(mean=stack.mean(axis=0),
                       sd=stack.std(axis=0) + 1e-12,
                       n_clean=len(rows), limit=limit,
                       description=f"{len(rows)} {description}")


#: z(0) above this says the carrier has more zeros than its source produces,
#: which is shrinkage and therefore F5 rather than a shrinkage-free variant.
#: Measured on 15 held-out carriers: clean -0.05, F5 +2.42, nsF5 -0.07.
SHRINKAGE_Z = 1.0


def name_the_member(model: SourceModel, data: bytes) -> Optional[Dict[str, float]]:
    """Distinguish F5 from its shrinkage-free variants using the source model.

    F5 decrements magnitudes, so a magnitude-1 coefficient becomes 0 and the
    zero bin gains. The shrinkage-free variant increments |1| to |2| instead,
    so the zero bin does not move and the |2| bin gains sharply. Measured mean
    z-scores over 15 held-out carriers at 0.15 bpp:

        bin        clean      F5     nsF5
        d=0        -0.05   +2.42    -0.07
        d=2        +0.72   -1.94   +11.76

    Discrimination between the two, given only stego carriers: AUC 1.000 on
    z(0) and on z(0) - z(2), against 0.622-0.736 for the carrier-derived
    calibration route.
    """
    z = model.z_scores(data)
    if z is None:
        return None
    return {"z_zero": float(z[0]), "z_one": float(z[1]), "z_two": float(z[2]),
            "shrinkage_statistic": float(z[0] - z[2]),
            "shrinkage": bool(z[0] >= SHRINKAGE_Z)}


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None,
           beta_threshold: float = -0.13,
           source_model: Optional[SourceModel] = None) -> Report:
    report = Report(carrier=name)
    est = estimate_change_rate(data)
    if est is None or est["beta"] < beta_threshold:
        return report

    member = name_the_member(source_model, data) if source_model else None
    level = cap_without_baseline(Evidence.E3, baseline)
    report.add(Finding(
        carrier=name, level=level, detector="f5_calibration",
        claim=(f"the calibrated AC histogram is displaced by "
               f"{est['beta'] - baseline.threshold if baseline else est['beta']:+.3f} "
               f"from the clean operating point, consistent with a "
               f"magnitude-decrementing embedder of the F5 family"),
        domain=DOMAIN if level >= Evidence.E3 else None,
        # With only the carrier-derived calibration, the family is
        # identifiable and the member is not. With a source model, the member
        # is too -- see name_the_member and gap G-20.
        algorithm=(None if level < Evidence.E3 else
                   "f5-family" if member is None else
                   "f5" if member["shrinkage"] else "f5-no-shrinkage"),
        baseline=baseline,
        detail={"beta": round(est["beta"], 5),
                "zero_excess": round(est["zero_excess"], 5),
                "beta_is_a_relative_statistic": True,
                "note": ("beta carries a stable calibration bias (clean mean "
                         "-0.152, sd 0.010 on this source), so it is usable "
                         "only against a measured clean baseline, never as an "
                         "absolute change rate"),
                "estimated_changed_coefficients":
                    int(max(est["beta"], 0.0) * sum(est["h_stego"][1:])),
                **({} if member is None else
                   {"source_model": source_model.description,
                    "z_zero": round(member["z_zero"], 3),
                    "z_two": round(member["z_two"], 3),
                    "shrinkage_detected": member["shrinkage"]})},
    ))
    return report


def build_sample(cover: bytes, rate: float = 0.5) -> bytes:
    return embed(cover, rate=rate)
