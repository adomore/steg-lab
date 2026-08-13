#!/usr/bin/env python3
"""Regenerate the working corpus from seeds and write the manifest.

No image bytes live in this repository. This script plus steganalysis.corpus
reproduces them exactly, which is what makes "same source" a checkable
property rather than a claim in a report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis import corpus  # noqa: E402

OUT = ROOT / "corpus" / "generated"
MANIFEST = ROOT / "corpus" / "manifest.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="check existing files against the manifest instead of writing")
    args = ap.parse_args()

    if args.verify:
        if not MANIFEST.exists():
            print("no manifest; run without --verify first")
            return 1
        problems = corpus.verify_manifest(MANIFEST, OUT)
        for p in problems:
            print("  " + p)
        print(f"{'FAIL' if problems else 'OK'}: {len(problems)} mismatch(es)")
        return 1 if problems else 0

    specs = corpus.default_specs()
    digests = corpus.write_corpus(specs, OUT)
    corpus.write_manifest(specs, digests, MANIFEST)
    print(f"wrote {len(specs)} covers to {OUT.relative_to(ROOT)}")
    print(f"manifest: {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
