"""Lab 08 -- LSB matching, and a lab whose detector does not exist.

This lab ships no working detector. That is not an omission; it is the
content.

LSB replacement can only ever move a value between the two members of one
pair -- 2i to 2i+1 or back. That constraint is a structure, and RS analysis,
Sample Pair Analysis and Weighted Stego are all estimators of how far it has
been eroded. LSB matching adds or subtracts one at random instead. The
change to the embedder is one line. The structure never forms, and the
entire family loses its signal at once.

Gate G4 measures exactly how completely: over 80 covers at five payloads,
every shipped detector stays within 0.086 of chance. Compare lab 07, where
Weighted Stego reaches AUC 1.000 at a quarter of a bit per pixel.

`detect` therefore returns E0 and says why. Reporting E1 on every image
because a stronger algorithm might be present would be a detector with a
100% false-positive rate wearing a disclaimer.

What actually works on LSB matching is distributional rather than
structural -- calibrated HCF centre of mass (Ker), SPAM and SRM features
with an ensemble classifier (T5), or a CNN (T6). The first was implemented
here and did not reach chance-plus-noise on this corpus; see gap G-12 and
the docstring of calibrated_hcf_com_UNVALIDATED. The honest position at P1
is that this repository cannot detect LSB matching, and T5 is where that
changes.

Domain    : spatial
Algorithm : lsb-matching
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis import detectors as D
from steganalysis import embedders as E
from steganalysis.evidence import Evidence, FalsePositiveBaseline, Finding, Report

NAME = "lsb_matching"
DOMAIN = "spatial"
ALGORITHM = "lsb-matching"


def _to_array(data: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(data)).convert("L"))


def _to_png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8), mode="L").save(
        buf, format="PNG", compress_level=6, optimize=False)
    return buf.getvalue()


def embed(cover: bytes, payload: bytes = b"", rate: float = 0.5,
          seed: int = 0) -> bytes:
    arr = _to_array(cover)
    return _to_png(E.lsb_matching(arr, rate, seed=seed).stego)


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None) -> Report:
    """Returns E0. See the module docstring: there is nothing honest to report."""
    return Report(carrier=name)


def separation(covers: List[bytes], rate: float = 0.5,
               detector: str = "rs_analysis") -> Dict[str, float]:
    """Measure how far from chance a structural detector gets. Used by the test.

    Returning the number rather than a boolean means the test asserts a
    measured quantity, and a future detector that genuinely works will move
    it rather than silently satisfying a weaker condition.
    """
    from sklearn.metrics import roc_auc_score

    fn = D.DETECTORS[detector]
    clean, stego = [], []
    for i, blob in enumerate(covers):
        arr = _to_array(blob)
        clean.append(float(fn(arr)))
        stego.append(float(fn(E.lsb_matching(arr, rate, seed=i).stego)))
    auc = float(roc_auc_score([0] * len(clean) + [1] * len(stego), clean + stego))
    return {"detector": detector, "rate": rate, "auc": auc,
            "deviation_from_chance": abs(auc - 0.5)}


def build_sample(cover: bytes, rate: float = 0.5) -> bytes:
    return embed(cover, rate=rate)
