#!/usr/bin/env python3
"""Run the checks that need a real machine, and print a verdict for each.

Four gaps in GAP_ANALYSIS.md cannot be closed in the build container: they
need a Kali box, a corpus download, or more compute than a sandbox turn allows.
This runs whichever of them the local machine can support, skips the rest with
a reason, and prints one block per gap that can be pasted back as-is.

Usage:
    python3 scripts/analyst-checks.py              # everything available
    python3 scripts/analyst-checks.py --only G-11
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RULE = "=" * 72


def header(gap: str, title: str) -> None:
    print(RULE)
    print(f"{gap} -- {title}")
    print(RULE)


def check_g8() -> None:
    header("G-8", "optional Kali tooling")
    script = ROOT / "scripts" / "setup-kali.sh"
    if not script.exists():
        print("SKIP: scripts/setup-kali.sh is missing")
        return
    # Two classes, and the distinction matters more than the count.
    #
    # A REFERENCE implementation is what a hand-written parser is checked
    # against. Its absence does not fail anything -- the test calls
    # pytest.mark.skipif and the suite still reports green. So a machine
    # missing ffmpeg runs the video tests without ever comparing against
    # ffmpeg's decoder, which is the single most valuable thing those tests do.
    # A silently skipped cross-validation reports the same green as a passing
    # one, and that is worth saying out loud.
    reference = {
        "pngcheck": "gate G1 PNG cross-check",
        "djpeg": "gate G1 JPEG cross-check",
        "tshark": "lab 21 pcap cross-check",
        "ffmpeg": "lab 22 pixel-for-pixel decoder comparison",
        "mkfs.vfat": "lab 23 volume construction",
        "mcopy": "lab 23 file writing",
    }
    optional = {
        "zsteg": "PNG/BMP triage",
        "steghide": "gate G0 active-warden check",
        "stegseek": "steghide passphrase recovery",
        "outguess": "JPEG embedding",
        "exiftool": "metadata triage",
        "binwalk": "container triage",
        "foremost": "carving",
    }

    print("  REFERENCE IMPLEMENTATIONS -- tests SKIP silently without these")
    missing_ref = []
    for name, why in reference.items():
        path = shutil.which(name)
        if not path:
            missing_ref.append(name)
        print(f"    {name:<11} {'OK' if path else 'MISSING':<8} {why}")
    print()
    print("  OPTIONAL TOOLING -- labs report reduced coverage without these")
    missing_opt = []
    for name, why in optional.items():
        path = shutil.which(name)
        if not path:
            missing_opt.append(name)
        print(f"    {name:<11} {'OK' if path else 'missing':<8} {why}")
    print()
    if missing_ref:
        print(f"VERDICT: {len(missing_ref)} reference implementation(s) absent: "
              f"{', '.join(missing_ref)}.")
        print("Until they are installed the suite passes WITHOUT cross-checking")
        print("those parsers against anything. Install them first:")
        print("  bash scripts/setup-kali.sh")
    elif missing_opt:
        print(f"VERDICT: all cross-checks available. Optional tools missing: "
              f"{', '.join(missing_opt)}")
        print("Run: INSTALL_OPTIONAL=1 bash scripts/setup-kali.sh")
    else:
        print("VERDICT: everything present -- G-8 can be closed.")


def check_g11() -> None:
    header("G-11", "is Sample Pair Analysis applicable to real photographs?")
    from steganalysis import reference
    from steganalysis.detectors import spa_asymmetry

    corpus = reference.load_registered()
    if corpus is None or not len(corpus):
        print("SKIP: no reference corpus registered.")
        print("Run: python3 scripts/register-corpus.py")
        return

    import numpy as np
    fractions, coefficients = [], []
    for image in corpus.sample(24, seed=77):
        report = spa_asymmetry(image)
        if report:
            fractions.append(report["m0_odd_fraction"])
            coefficients.append(report["m0_coefficient"] / max(report["m0_pairs"], 1))

    if not fractions:
        print("SKIP: no usable images")
        return
    mean = float(np.mean(fractions))
    print(f"  images                 : {len(fractions)}")
    print(f"  m0_odd_fraction  mean  : {mean:.4f}")
    print(f"                   range : {min(fractions):.4f} .. {max(fractions):.4f}")
    print(f"  normalised coefficient : {float(np.mean(coefficients)):+.4f}")
    print()
    print("  Every trace-set equation collapses to an identity when the cover's")
    print("  LSBs are unbiased. The asymmetry can only live at m=0, and it shows")
    print("  up as an odd fraction well below 0.5.")
    print()
    if mean < 0.47:
        print(f"VERDICT: APPLICABLE (mean {mean:.4f} < 0.47). The remaining work is")
        print("one cover assumption; spa_synthetic_pairs will check any candidate.")
    else:
        print(f"VERDICT: NOT APPLICABLE (mean {mean:.4f}). Trace sets are the wrong")
        print("parameterisation for this source -- worth more than a fourth attempt")
        print("at reconstructing the estimator.")


def check_g18() -> None:
    header("G-18", "second acquisition pipeline")
    from steganalysis import reference

    root = reference.default_root()
    candidates = sorted(p.name for p in root.iterdir()) if root.exists() else []
    print(f"  corpus/reference/ contains: {candidates or '(empty)'}")
    alaska = [c for c in candidates if "alaska" in c.lower()]
    print()
    if alaska:
        try:
            corpus = reference.discover(root / alaska[0], name="alaska2")
            report = reference.verify(corpus, check=12)
            print(f"  files={report['files']} shapes={report['shapes']}")
            print(f"  lag-1 correlation={report['lag1_correlation']} "
                  f"photographic={report['photographic']}")
            print()
            print("VERDICT: ALASKA2 present and readable. Run G5 with it as the")
            print("test source to close the acquisition half of G-18.")
        except Exception as exc:                      # noqa: BLE001
            print(f"VERDICT: found {alaska[0]} but could not read it: {exc}")
    else:
        print("VERDICT: no ALASKA2 drop found. The PROCESSING half of G-18 is")
        print("already closed -- reference.PIPELINES plus")
        print("  python3 gates/g5_feature_sets.py --corpus real --all-pipelines")
        print("The ACQUISITION half needs the download:")
        print("  https://www.kaggle.com/c/alaska2-image-steganalysis/data")


def check_g21() -> None:
    header("G-21", "does the ABS activation help at a larger carrier size?")
    from steganalysis import reference

    if reference.load_registered() is None:
        print("SKIP: no reference corpus registered.")
        print("Run: python3 scripts/register-corpus.py")
        return
    print("  This one is a run, not a measurement the script can shortcut:")
    print("  three ablation variants at 128px exceed a sandbox turn, which is")
    print("  why it is still open.")
    print()
    print("  python3 gates/g6_deep_learning.py \\")
    print("      --corpus real --side 128 --n 300 --epochs 40")
    print()
    print("  ABS did not replicate at 64px on either corpus (ReLU measured")
    print("  0.006 better on synthetic, 0.023 on BOSSbase). Two independent")
    print("  corpora, so a third result at a larger carrier settles whether it")
    print("  is a scale effect or the claim does not hold in this architecture.")
    print()
    print("VERDICT: ready to run; paste criterion D's block back.")


CHECKS = {"G-8": check_g8, "G-11": check_g11, "G-18": check_g18,
          "G-21": check_g21}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="run one gap, e.g. G-11")
    args = ap.parse_args()

    selected = ([args.only] if args.only else list(CHECKS))
    for gap in selected:
        if gap not in CHECKS:
            print(f"unknown gap {gap}; known: {', '.join(CHECKS)}")
            return 1
        try:
            CHECKS[gap]()
        except Exception as exc:                      # noqa: BLE001
            print(f"ERROR in {gap}: {type(exc).__name__}: {exc}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
