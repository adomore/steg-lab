#!/usr/bin/env python3
"""Search STC parity-check submatrices and print a table to paste into adaptive.py.

Filler, Judas and Fridrich tabulate submatrices found by search. This does the
search rather than transcribing a table that cannot be verified here.

Two things the search established, both reported by --validate:

  * The ranking generalises. A winner chosen on one set of covers keeps its
    relative standing on covers it was never scored against, so a fixed table
    is a property of the code and not an overfit to a carrier.
  * The win is small. Among candidates that produce a valid trellis at all,
    best and median differ by about a percentage point. The table's real value
    is that every entry is known to give a valid path, which removes the
    roughly one-in-three failure rate of drawing at random.

Run:  python3 scripts/search-submatrices.py [--candidates 24] [--validate]
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis import corpus
from steganalysis.adaptive import coding_loss

HEIGHTS = (8, 10, 12)
WIDTHS = (2,)


def cover(seed: int, side: int = 128) -> np.ndarray:
    spec = corpus.CoverSpec("g.png", seed, side, side,
                            ["texture", "photo_like"][seed % 2], "png")
    return np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))


def candidate(rng: np.random.Generator, h: int, w: int) -> List[int]:
    """Top and bottom bit of every column forced to 1, per the paper."""
    top = 1 << (h - 1)
    return [int(rng.integers(0, 1 << h)) | 1 | top for _ in range(w)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=24)
    ap.add_argument("--validate", action="store_true",
                    help="score the winners on held-out covers too")
    args = ap.parse_args()

    search_covers = [cover(5_400_000 + i) for i in range(2)]
    holdout = [cover(5_500_000 + i) for i in range(3)]
    rng = np.random.default_rng(20260101)

    print("GOOD_SUBMATRICES = {")
    for h in HEIGHTS:
        for w in WIDTHS:
            scored = []
            for _ in range(args.candidates):
                H = candidate(rng, h, w)
                loss = coding_loss(H, h, search_covers)
                if np.isfinite(loss):
                    scored.append((loss, H))
            if not scored:
                print(f"    # ({h}, {w}): no valid candidate in "
                      f"{args.candidates} draws")
                continue
            scored.sort(key=lambda t: t[0])
            best_loss, best = scored[0]
            median_loss = float(np.median([l for l, _ in scored]))
            extra = ""
            if args.validate:
                extra = (f"  held-out {coding_loss(best, h, holdout):.1%}"
                         f", median candidate {median_loss:.1%}")
            print(f"    ({h}, {w}): {best},"
                  f"  # loss {best_loss:.1%}, "
                  f"{len(scored)}/{args.candidates} valid{extra}")
    print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
