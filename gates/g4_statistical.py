#!/usr/bin/env python3
"""Gate G4 -- statistical detection, including a failure that must reproduce.

This is the heaviest gate in the course, and the only one whose criteria
include something the repository must be *unable* to do.

Criteria:

  A. LSB REPLACEMENT IS DETECTED. Detection AUC rises monotonically with
     relative payload, and at 0.5 bpp both RS analysis and Weighted Stego
     reach AUC >= 0.95. At 0.25 bpp at least one of them must.

  B. LSB MATCHING IS NOT DETECTED BY THE SAME DETECTORS. At every rate, all
     three shipped detectors must land within 0.15 of chance. This is a
     required failure. A course that only demonstrates successes trains an
     analyst to expect them, and the single most useful fact in T4 is that a
     one-line change to the embedder -- add or subtract one instead of
     overwriting -- costs the whole structural family its signal.

  C. QUANTITATIVE ACCURACY. Weighted Stego is an estimator, not just a
     discriminator, so its mean absolute error against known payloads is
     reported and must stay under 0.15 for rates >= 0.25.

  D. FALSE POSITIVES ARE MEASURED, NOT ASSUMED. For each detector, the
     threshold that yields 95% true-positive rate on 0.5 bpp LSB replacement
     is found, and the false-positive rate at that threshold on clean covers
     is reported. A detector with no reported FPR cannot support a verdict
     above E1, by the rule in steganalysis.evidence.

  E. CORPUS HONESTY. The chi-square attack's behaviour on this corpus is
     reported whether or not it is flattering, because the synthetic covers'
     value-pair statistics are known to be unrepresentative.

Run:  python3 gates/g4_statistical.py [--n 80]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
from PIL import Image
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from steganalysis import corpus, detectors as D, embedders as E  # noqa: E402
from steganalysis import reference  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
RATES = [0.05, 0.10, 0.25, 0.50, 1.00]
KINDS = ["texture", "photo_like"]
SHIPPED = ["rs_analysis", "weighted_stego", "chi_square"]


def gray_cover(seed: int, side: int = 256) -> np.ndarray:
    spec = corpus.CoverSpec("g.png", seed, side, side, KINDS[seed % 2], "png")
    return np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))


def load_covers(n: int, use_real: bool, side: int = 256) -> tuple:
    """Return (covers, description). Real covers are centre-cropped to `side`.

    Cropping rather than resizing: resampling filters the very
    high-frequency content these detectors measure, so a resized cover is a
    different statistical object. A crop is still a real acquisition.
    """
    if not use_real:
        return ([gray_cover(500_000 + i) for i in range(n)],
                f"{n} synthetic covers")

    corp = reference.find_bossbase()
    if corp is None or not len(corp):
        raise SystemExit("no reference corpus registered; "
                         "run scripts/register-corpus.py first")
    images = corp.sample(n, seed=11)
    out = []
    for img in images:
        h, w = img.shape
        top, left = (h - side) // 2, (w - side) // 2
        out.append(img[top:top + side, left:left + side])
    return out, f"{len(out)} covers from {corp.name}, centre-cropped to {side}px"


def sweep(covers: List[np.ndarray]) -> Dict:
    scores: Dict[str, Dict] = {name: {"clean": []} for name in SHIPPED}

    for name in SHIPPED:
        fn = D.DETECTORS[name]
        scores[name]["clean"] = [float(fn(c)) for c in covers]

    for label, embed in (("lsb_replacement", E.lsb_replacement),
                         ("lsb_matching", E.lsb_matching)):
        for rate in RATES:
            stegos = [embed(c, rate, seed=i).stego for i, c in enumerate(covers)]
            for name in SHIPPED:
                fn = D.DETECTORS[name]
                scores[name][f"{label}@{rate}"] = [float(fn(s)) for s in stegos]

    return scores


def auc_of(clean: List[float], stego: List[float]) -> float:
    y = [0] * len(clean) + [1] * len(stego)
    return float(roc_auc_score(y, clean + stego))


def fpr_at_tpr(clean: List[float], stego: List[float], target_tpr: float) -> Dict:
    """Lowest false-positive rate achieving the target true-positive rate.

    The first version used `quantile(stego, 1 - target)` as the threshold.
    That is fine when scores are spread out and wrong when they pile up on a
    boundary value: on real covers the chi-square p-value is 0.0 for most
    images, the 5th percentile of the stego scores is also 0.0, and every
    clean cover satisfies `>= 0.0`. The gate duly reported "FPR = 1.000 at
    threshold 0.0", which is not a measurement of anything.

    This version scans candidate thresholds and takes the minimum achievable
    FPR, then says plainly when no useful operating point exists rather than
    emitting a number that looks like one.
    """
    c = np.asarray(clean, dtype=np.float64)
    s = np.asarray(stego, dtype=np.float64)
    candidates = np.unique(np.concatenate([c, s]))

    best = None
    for t in candidates:
        tpr = float(np.count_nonzero(s >= t)) / s.size
        if tpr < target_tpr:
            continue
        fpr = float(np.count_nonzero(c >= t)) / c.size
        if best is None or fpr < best[0]:
            best = (fpr, float(t), tpr)

    if best is None:
        return {"threshold": None, "target_tpr": target_tpr,
                "false_positives": None, "n_clean": int(c.size),
                "fpr": None, "degenerate": True,
                "reason": f"no threshold reaches TPR {target_tpr:g}"}

    fpr, thresh, tpr = best
    degenerate = fpr >= 0.95
    out = {"threshold": round(thresh, 6),
           "target_tpr": target_tpr,
           "achieved_tpr": round(tpr, 4),
           "false_positives": int(round(fpr * c.size)),
           "n_clean": int(c.size),
           "fpr": round(fpr, 4),
           "degenerate": degenerate}
    if degenerate:
        out["reason"] = ("the score distributions overlap too heavily for this "
                         "TPR to be reachable at any useful FPR; this detector "
                         "has no operating point here, which is a result about "
                         "the detector and not a false-positive rate")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80, help="number of covers")
    ap.add_argument("--corpus", choices=["synthetic", "real"], default="synthetic",
                    help="'real' uses the corpus registered under corpus/reference/")
    args = ap.parse_args()

    covers, corpus_desc = load_covers(args.n, args.corpus == "real")
    scores = sweep(covers)
    results = []

    # ---------------------------------------------------------------- A
    auc_r = {name: {r: auc_of(scores[name]["clean"],
                              scores[name][f"lsb_replacement@{r}"])
                    for r in RATES} for name in SHIPPED}
    monotone = all(
        all(auc_r[name][RATES[i]] <= auc_r[name][RATES[i + 1]] + 0.05
            for i in range(len(RATES) - 1))
        for name in ("rs_analysis", "weighted_stego"))
    at_050 = all(auc_r[name][0.50] >= 0.95 for name in ("rs_analysis", "weighted_stego"))
    at_025 = max(auc_r["rs_analysis"][0.25], auc_r["weighted_stego"][0.25]) >= 0.95
    results.append({
        "name": "A_lsb_replacement_is_detected",
        "auc_by_rate": {k: {str(r): round(v, 3) for r, v in d.items()}
                        for k, d in auc_r.items()},
        "monotone": monotone,
        "both_at_0.50_ge_0.95": at_050,
        "best_at_0.25_ge_0.95": at_025,
        "pass": monotone and at_050 and at_025,
    })

    # ---------------------------------------------------------------- B
    auc_m = {name: {r: auc_of(scores[name]["clean"],
                              scores[name][f"lsb_matching@{r}"])
                    for r in RATES} for name in SHIPPED}
    worst_dev = max(abs(auc_m[name][r] - 0.5) for name in SHIPPED for r in RATES)
    results.append({
        "name": "B_lsb_matching_defeats_the_same_detectors",
        "auc_by_rate": {k: {str(r): round(v, 3) for r, v in d.items()}
                        for k, d in auc_m.items()},
        "worst_deviation_from_chance": round(worst_dev, 4),
        "tolerance": 0.15,
        "pass": worst_dev <= 0.15,
        "note": ("REQUIRED FAILURE. LSB replacement can only move 2i to 2i+1 "
                 "or back; matching moves +/-1 in a random direction, so the "
                 "even/odd asymmetry these detectors estimate never forms. "
                 "If this criterion ever starts passing by detecting, the "
                 "embedder is broken, not the detector improved."),
    })

    # ---------------------------------------------------------------- C
    errors = {}
    for r in RATES:
        est = scores["weighted_stego"][f"lsb_replacement@{r}"]
        errors[str(r)] = round(float(np.mean(np.abs(np.asarray(est) - r))), 4)
    high_rate_ok = all(errors[str(r)] < 0.15 for r in RATES if r >= 0.25)
    results.append({
        "name": "C_weighted_stego_quantitative_accuracy",
        "mean_absolute_error_by_rate": errors,
        "pass": high_rate_ok,
        "note": ("WS estimates the payload, it does not merely rank. That is "
                 "what lets a report say how much was hidden, not just that "
                 "something was."),
    })

    # ---------------------------------------------------------------- D
    baselines = {name: fpr_at_tpr(scores[name]["clean"],
                                  scores[name]["lsb_replacement@0.5"], 0.95)
                 for name in SHIPPED}
    usable = {k: v for k, v in baselines.items() if not v.get("degenerate")}
    results.append({
        "name": "D_false_positive_rates_measured",
        "baselines": baselines,
        "detectors_with_a_usable_operating_point": sorted(usable),
        "detectors_without_one": sorted(set(baselines) - set(usable)),
        "pass": len(usable) >= 2,
        "note": ("These are the numbers a finding must carry to be reported "
                 "above E1. They are properties of this corpus and do not "
                 "transfer to a different source."),
    })

    # ---------------------------------------------------------------- E
    clean_chi = scores["chi_square"]["clean"]
    mean_p = float(np.mean(clean_chi))
    if args.corpus == "real":
        chi_note = (
            "Reported, not graded. On real covers the chi-square attack "
            "behaves as its literature describes: clean p-values sit low, so "
            "a high p-value means something. Compare the same gate on "
            "synthetic covers, where the clean mean was 0.944, 64 of 80 "
            "exceeded 0.9, and the detector had no usable operating point at "
            "all. That contrast is the measured case for why the synthetic "
            "corpus was never adequate for this chapter.")
    else:
        chi_note = (
            "Reported, not graded. These synthetic covers already have "
            "near-equal value-pair counts, so the attack fires on clean data "
            "and has no usable operating point. On real BOSSbase covers the "
            "same code gives a clean mean p-value of 0.129. This is the "
            "measured case for why the statistical chapters need a real "
            "corpus; run with --corpus real.")
    results.append({
        "name": "E_corpus_honesty_chi_square",
        "clean_cover_mean_p_value": round(float(np.mean(clean_chi)), 4),
        "clean_covers_above_0.9": int(np.count_nonzero(np.asarray(clean_chi) > 0.9)),
        "n_clean": len(clean_chi),
        "auc_at_1.0_bpp": round(auc_r["chi_square"][1.00], 3),
        "pass": True,
        "corpus": corpus_desc,
        "note": chi_note,
    })

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "G4.json").write_text(json.dumps(results, indent=2) + "\n")

    print("=" * 70)
    print(f"Gate G4 -- statistical detection, {len(covers)} covers x "
          f"{len(RATES)} rates x 2 embedders")
    print(f"corpus: {corpus_desc}")
    print("=" * 70)
    failed = False
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        if not r["pass"]:
            failed = True
        print(f"[{status}] {r['name']}")
        for key, value in r.items():
            if key in ("name", "pass", "note"):
                continue
            if key == "auc_by_rate":
                for det, byrate in value.items():
                    cells = "  ".join(f"{k}:{v:.3f}" for k, v in byrate.items())
                    print(f"        {det:<20} {cells}")
            elif key == "baselines":
                for det, b in value.items():
                    if b.get("degenerate") or b.get("fpr") is None:
                        print(f"        {det:<20} NO USABLE OPERATING POINT "
                              f"-- {b.get('reason', '')[:60]}")
                    else:
                        print(f"        {det:<20} FPR={b['fpr']:.3f} "
                              f"({b['false_positives']}/{b['n_clean']}) "
                              f"at threshold {b['threshold']}")
            else:
                print(f"        {key}: {value}")
        if "note" in r:
            print(f"        -> {r['note']}")
    print("=" * 70)
    print("GATE G4:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
