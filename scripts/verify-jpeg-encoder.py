#!/usr/bin/env python3
"""Verify the JPEG entropy encoder -- gap G-14's acceptance check.

Three properties, each of which can fail independently:

  1. ROUND TRIP IS COEFFICIENT-EXACT. Decode, re-encode without changes,
     decode again; every DCT coefficient must be identical. Pixel equality
     is not enough -- two different coefficient sets can decode to similar
     pixels, and a steganographic payload lives in the coefficients.
  2. THE OUTPUT IS A REAL JPEG. libjpeg's djpeg must accept it, not just
     Pillow. One decoder agreeing with the encoder that wrote the file
     proves less than it appears to.
  3. EMBEDDED PAYLOADS SURVIVE. Modified coefficients must come back out of
     the written file unchanged, which is the only property the C-group
     labs actually need.

Run:  python3 scripts/verify-jpeg-encoder.py [--n 8]
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis import corpus, embedders as E  # noqa: E402
from steganalysis.jpeg_encode import coefficients_of, recode  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args()

    kinds = ["texture", "photo_like", "gradient"]
    qualities = [70, 80, 90, 95]
    failures = []
    sizes = []

    for i in range(args.n):
        blob = corpus.render(corpus.CoverSpec(
            f"v{i}.jpg", 990_000 + i, 192 + (i % 3) * 32, 128 + (i % 2) * 32,
            kinds[i % 3], "jpeg", quality=qualities[i % 4]))

        try:
            out = recode(blob)
        except Exception as exc:
            failures.append(f"carrier {i}: encode raised {exc}")
            continue

        before, after = coefficients_of(blob), coefficients_of(out)
        if after is None:
            failures.append(f"carrier {i}: output is not decodable")
            continue
        for cid in before:
            if not np.array_equal(before[cid], after[cid]):
                failures.append(f"carrier {i}: component {cid} coefficients changed")

        pa = np.array(Image.open(io.BytesIO(blob)).convert("RGB"))
        pb = np.array(Image.open(io.BytesIO(out)).convert("RGB"))
        if not np.array_equal(pa, pb):
            failures.append(f"carrier {i}: pixels differ after round trip")

        if shutil.which("djpeg"):
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "o.jpg"
                path.write_bytes(out)
                proc = subprocess.run(["djpeg", "-outfile", "/dev/null", str(path)],
                                      capture_output=True)
                if proc.returncode != 0:
                    failures.append(f"carrier {i}: djpeg rejected the output")

        sizes.append(len(out) / len(blob))

        for name, fn in (("jsteg", lambda c: E.jsteg(c, 0.8, seed=i).stego),
                         ("f5", lambda c: E.f5(c, 0.5, k=3, seed=i).stego)):
            want = fn(coefficients_of(blob)[1])
            got = coefficients_of(recode(blob, transform=fn, component=1))[1]
            if not np.array_equal(want, got):
                failures.append(f"carrier {i}: {name} payload did not survive")

    print("=" * 70)
    print(f"JPEG encoder verification -- {args.n} carriers")
    print("=" * 70)
    print(f"round trips checked   : {args.n}")
    print(f"djpeg available       : {bool(shutil.which('djpeg'))}")
    if sizes:
        print(f"mean size vs original : {np.mean(sizes):.2f}x "
              f"(optimal Huffman tables)")
    print(f"failures              : {len(failures)}")
    for f in failures[:10]:
        print("  " + f)
    print("=" * 70)
    print("JPEG ENCODER:", "FAIL" if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
