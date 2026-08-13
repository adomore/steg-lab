"""Lab 09 -- the first detector that cannot be shipped as a function.

Labs 01 to 08 exposed `detect(data, name, baseline)` and that was the whole
detector. This one cannot, and the reason is the content of T5.

A feature-set classifier has no fixed decision rule. It has a decision rule
*for a source*, learned from covers of that source. Ship it pre-trained and
you have shipped a detector calibrated to somebody else's camera. Gate G5
measured what that costs: training on one image family and testing on
another moves P_E from 0.140 to 0.487, which is chance. The classifier does
not degrade gracefully across sources; it stops working.

So `detect` here requires a `classifier` argument and returns E0 without
one. That is not an API inconvenience. It is the API telling the truth about
what this method needs, and the reason the evidence ladder demands a
same-source baseline rather than merely recommending one.

Domain    : spatial
Algorithm : any (SPAM models the cover, not the embedder)
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis import embedders as E
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)
from steganalysis.features import FldEnsemble, min_error_probability, spam686

NAME = "feature_based"
DOMAIN = "spatial"
ALGORITHM = "embedder-agnostic"


def _to_array(data: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(data)).convert("L"))


def _to_png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8), mode="L").save(
        buf, format="PNG", compress_level=6, optimize=False)
    return buf.getvalue()


def embed(cover: bytes, payload: bytes = b"", rate: float = 1.0,
          seed: int = 0, matching: bool = True) -> bytes:
    arr = _to_array(cover)
    fn = E.lsb_matching if matching else E.lsb_replacement
    return _to_png(fn(arr, rate, seed=seed).stego)


def features(data: bytes) -> np.ndarray:
    return spam686(_to_array(data))


def train(covers: Sequence[bytes], rate: float = 1.0, matching: bool = True,
          seed: int = 1) -> FldEnsemble:
    """Train on covers from the source under examination. Never on other covers."""
    arrays = [_to_array(c) for c in covers]
    fn = E.lsb_matching if matching else E.lsb_replacement
    fc = np.array([spam686(a) for a in arrays])
    fs = np.array([spam686(fn(a, rate, seed=seed + i).stego)
                   for i, a in enumerate(arrays)])
    return FldEnsemble(n_learners=40, d_sub=200, seed=seed).fit(fc, fs)


def calibrate(classifier: FldEnsemble, covers: Sequence[bytes],
              rate: float = 1.0, matching: bool = True,
              seed: int = 7000) -> dict:
    """Find the operating threshold and its error rates on held-out covers."""
    arrays = [_to_array(c) for c in covers]
    fn = E.lsb_matching if matching else E.lsb_replacement
    fc = np.array([spam686(a) for a in arrays])
    fs = np.array([spam686(fn(a, rate, seed=seed + i).stego)
                   for i, a in enumerate(arrays)])
    sc = classifier.decision_function(fc)
    ss = classifier.decision_function(fs)
    pe, threshold = min_error_probability(sc, ss)
    fp = int(np.count_nonzero(sc >= threshold))
    return {"P_E": pe, "threshold": threshold,
            "false_positives": fp, "n_clean": len(sc)}


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None,
           classifier: Optional[FldEnsemble] = None,
           threshold: float = 0.5) -> Report:
    report = Report(carrier=name)
    if classifier is None:
        return report

    score = float(classifier.decision_function(features(data)[None, :])[0])
    if score < threshold:
        return report

    level = cap_without_baseline(Evidence.E3, baseline)
    report.add(Finding(
        carrier=name, level=level, detector="spam686_fld_ensemble",
        claim=(f"{score:.0%} of base learners vote stego, above the "
               f"calibrated threshold {threshold:.2f}"),
        domain=DOMAIN if level >= Evidence.E3 else None,
        algorithm=ALGORITHM if level >= Evidence.E3 else None,
        baseline=baseline,
        detail={"vote_fraction": round(score, 4), "threshold": threshold,
                "feature_set": "SPAM686", "n_base_learners": len(classifier.learners)},
    ))
    return report


def build_sample(cover: bytes, rate: float = 1.0) -> bytes:
    return embed(cover, rate=rate)
