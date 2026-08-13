#!/usr/bin/env python3
"""Register a real corpus so the gates can find and trust it.

Nothing is downloaded. This inspects whatever is under corpus/reference/,
checks it is the dataset it claims to be, and writes an index the gates read.

Usage:
    python3 scripts/register-corpus.py
    python3 scripts/register-corpus.py --source /path/to/BOSSbase_1.01.zip
    python3 scripts/register-corpus.py --check 64
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis.reference import (CorpusError, default_root,  # noqa: E402
                                    discover, find_bossbase, verify,
                                    write_index)

INDEX = ROOT / "corpus" / "reference" / "index.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="",
                    help="directory or .zip; defaults to searching corpus/reference/")
    ap.add_argument("--check", type=int, default=24,
                    help="how many images to read while verifying")
    ap.add_argument("--name", default="bossbase")
    args = ap.parse_args()

    root = default_root()
    root.mkdir(parents=True, exist_ok=True)

    try:
        corpus = (discover(Path(args.source), name=args.name) if args.source
                  else find_bossbase(root))
    except CorpusError as exc:
        print(f"FAIL: {exc}")
        return 1

    if corpus is None or not len(corpus):
        print("=" * 70)
        print("No reference corpus found.")
        print("=" * 70)
        print(f"Expected a directory or .zip of PGM images under:")
        print(f"  {root.relative_to(ROOT)}/")
        print()
        print("BOSSbase 1.01 (10,000 grayscale 512x512 PGM):")
        print("  http://dde.binghamton.edu/download/ImageDB/BOSSbase_1.01.zip")
        print()
        print("Leave the archive zipped if disk is tight -- 1.6 GB compressed")
        print("against about 2.6 GB unpacked, and the loader reads zip members")
        print("directly. See scripts/get-corpora.sh for licensing.")
        return 1

    report = verify(corpus, check=args.check)
    write_index(corpus, report, INDEX)

    print("=" * 70)
    print(f"Reference corpus: {report['name']}")
    print("=" * 70)
    print(f"source                : {report['source']}")
    print(f"read from zip directly: {report['is_zip']}")
    print(f"files                 : {report['files']}")
    print(f"images verified       : {report['checked']}")
    print(f"dimensions seen       : {report['shapes']}")
    print(f"distinct digests      : {report['unique_digests']} of {report['checked']}")
    print(f"lag-1 correlation     : {report['lag1_correlation']} "
          f"({'photographic' if report['photographic'] else 'NOT PHOTOGRAPHIC'})")
    if report["camera_counts"]:
        print("camera partition      : "
              f"{'consistent' if report['camera_partition_consistent'] else 'INCONSISTENT'}")
        for cam, count in report["camera_counts"].items():
            print(f"    {cam:<22} {count}")
        print("    (secondary source -- confirm against the dataset README)")
    if report["problems"]:
        print("problems:")
        for prob in report["problems"]:
            print(f"    {prob}")
    print(f"index written         : {INDEX.relative_to(ROOT)}")
    print("=" * 70)
    print("CORPUS:", "USABLE" if report["usable"] else "NOT USABLE")

    if report["usable"]:
        print()
        print("Gates can now run against it:")
        print("  python3 gates/g4_statistical.py --corpus real --n 200")
        print("  python3 gates/g5_feature_sets.py --corpus real --n 400")
    return 0 if report["usable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
