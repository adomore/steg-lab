#!/usr/bin/env python3
"""Regenerate the working corpus from seeds and check it against the manifest.

No image bytes live in this repository. This script plus steganalysis.corpus
reproduces them, which is what makes "same source" a checkable property rather
than a claim in a report.

Three modes, and the distinction is the point:

  (default)           render the covers, then compare them to the COMMITTED
                      manifest. Drift is a hard failure.
  --verify            hash the files already on disk against the manifest.
  --update-manifest   re-lock the digests. Only correct when the drift is
                      understood and the gates have been re-run.

The default used to overwrite the manifest on every run. That made the CI pair
`generate.py` then `generate.py --verify` self-referential: it verified the
manifest it had just written, so it could prove a single run agreed with
itself and could never detect drift away from the committed digests. Measured:
under zlib 1.3.1 all 12 PNG covers drifted from the v1.0.0 manifest and the
pair still reported OK.
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
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true",
                    help="check existing files against the manifest instead of writing")
    ap.add_argument("--update-manifest", action="store_true",
                    help="re-lock the digests to what this toolchain renders")
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
    print(f"wrote {len(specs)} covers to {OUT.relative_to(ROOT)}")

    if args.update_manifest or not MANIFEST.exists():
        corpus.write_manifest(specs, digests, MANIFEST)
        print(f"manifest written: {MANIFEST.relative_to(ROOT)}")
        return 0

    # Compare, never silently rewrite. A manifest that follows the renderer
    # around locks nothing.
    drift = corpus.manifest_drift(MANIFEST, digests)
    if not drift:
        print(f"manifest matches: {MANIFEST.relative_to(ROOT)}")
        return 0

    print(f"\nDRIFT from {MANIFEST.relative_to(ROOT)}:")
    for d in drift:
        print("  " + d)
    print("\nThe corpus this machine renders is not the corpus the manifest "
          "pins, so\nany false-positive baseline measured here is not "
          "same-source with one\nmeasured elsewhere. Decide which it is:")
    print("  * encoder changed  -- expected across distributions for PNG; "
          "re-lock with\n"
          "                        --update-manifest AND re-run the gates, "
          "because the\n"
          "                        thresholds were measured on the old bytes.")
    print("  * renderer changed -- a real regression in steganalysis.corpus; "
          "fix it\n"
          "                        rather than re-locking.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
