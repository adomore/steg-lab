#!/usr/bin/env python3
"""Gate G2 -- classical embedding algorithms, measured against their theory.

T2 makes arithmetic claims about matrix encoding. Arithmetic claims are the
easiest kind to check and the easiest kind to get subtly wrong, so this gate
checks them against real DCT coefficients rather than against a simulation.

Criteria:

  A. Embedding efficiency matches k / (1 - 2^-k) within 2% for k in
     {1, 2, 3, 4}, measured on the shrinkage-free variant. This is pure
     matrix-encoding arithmetic; if it is off, every statement in T2 about
     the payload-vs-detectability trade is off with it.

  B. Embedding rate matches k / (2^k - 1) bits per coefficient within 5%,
     same variant. Efficiency alone can be faked by embedding less; the rate
     pins it down.

  NOTE ON A AND B. Both criteria originally ran against plain F5 and failed
  by a consistent ~45%. That was not an implementation defect: a shrinkage
  event spends a coefficient change and carries no bits, because the block
  is re-sent. Plain F5 therefore *cannot* meet the textbook figures, and a
  gate that demanded it would have been testing the wrong object. The
  criteria now measure the code where the arithmetic actually applies, and
  the shortfall becomes criterion C's subject rather than a failure.

  C. The shrinkage penalty, quantified. Plain F5 must show shrinkage events
     and the variant must show none, and the efficiency and rate lost to
     shrinkage are reported as numbers. This is the real argument for nsF5 --
     stronger than the histogram notch, because it costs payload.

  D. Jsteg equalises the histogram pairs it touches and leaves the pair it
     skips alone. The skip rule is Jsteg's fingerprint, so it has to show.

Run:  python3 gates/g2_classical.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from steganalysis import corpus, embedders as E  # noqa: E402
from steganalysis import jpeg as jpeg_mod  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
N_CARRIERS = 8


def load_coefficients(n: int = N_CARRIERS) -> List[np.ndarray]:
    """Real quantised DCT coefficients from decoded JPEG carriers."""
    out = []
    for i in range(n):
        blob = corpus.render(corpus.CoverSpec(
            f"g2_{i}.jpg", 400_000 + i, 256, 256,
            ["texture", "photo_like"][i % 2], "jpeg", quality=[80, 90, 95][i % 3]))
        parsed = jpeg_mod.parse_jpeg(blob)
        decoded = jpeg_mod.decode_scan(parsed, collect_coefficients=True)
        if not decoded.supported:
            continue
        # Luma only; chroma planes are quantised far more coarsely and
        # would mix two very different coefficient distributions.
        out.append(decoded.coefficients[1])
    return out


def criterion_a_efficiency(coeff_sets: List[np.ndarray]) -> Dict:
    rows = []
    worst = 0.0
    for k in (1, 2, 3, 4):
        effs = []
        for i, coeffs in enumerate(coeff_sets):
            res = E.f5(coeffs, rate=0.30, k=k, seed=100 + i, no_shrinkage=True)
            if res.changes:
                effs.append(res.embedding_efficiency)
        measured = float(np.mean(effs))
        theory = k / (1.0 - 2.0 ** (-k))
        err = abs(measured - theory) / theory
        worst = max(worst, err)
        rows.append({"k": k, "theory": round(theory, 4),
                     "measured": round(measured, 4),
                     "relative_error": round(err, 5)})
    return {"name": "A_f5_embedding_efficiency", "rows": rows,
            "worst_relative_error": round(worst, 5), "tolerance": 0.02,
            "pass": worst <= 0.02}


def criterion_b_rate(coeff_sets: List[np.ndarray]) -> Dict:
    rows = []
    worst = 0.0
    for k in (1, 2, 3, 4):
        rates = []
        for i, coeffs in enumerate(coeff_sets):
            res = E.f5(coeffs, rate=1.0, k=k, seed=200 + i, no_shrinkage=True)
            nonzero = int(np.count_nonzero(coeffs))
            if nonzero:
                rates.append(res.bits_embedded / nonzero)
        measured = float(np.mean(rates))
        theory = k / (2 ** k - 1)
        err = abs(measured - theory) / theory
        worst = max(worst, err)
        rows.append({"k": k, "theory": round(theory, 4),
                     "measured": round(measured, 4),
                     "relative_error": round(err, 5)})
    return {"name": "B_f5_embedding_rate", "rows": rows,
            "worst_relative_error": round(worst, 5), "tolerance": 0.05,
            "pass": worst <= 0.05}


def criterion_c_shrinkage(coeff_sets: List[np.ndarray]) -> Dict:
    plain_events = 0
    ns_events = 0
    eff_plain, eff_ns, rate_plain, rate_ns = [], [], [], []

    for i, coeffs in enumerate(coeff_sets):
        nonzero = int(np.count_nonzero(coeffs))
        plain = E.f5(coeffs, rate=1.0, k=3, seed=300 + i)
        ns = E.f5(coeffs, rate=1.0, k=3, seed=300 + i, no_shrinkage=True)

        plain_events += plain.shrinkage_events
        ns_events += ns.shrinkage_events
        if plain.changes:
            eff_plain.append(plain.embedding_efficiency)
        if ns.changes:
            eff_ns.append(ns.embedding_efficiency)
        if nonzero:
            rate_plain.append(plain.bits_embedded / nonzero)
            rate_ns.append(ns.bits_embedded / nonzero)

    ep, en = float(np.mean(eff_plain)), float(np.mean(eff_ns))
    rp, rn = float(np.mean(rate_plain)), float(np.mean(rate_ns))

    ok = (plain_events > 0 and ns_events == 0 and ep < en and rp < rn)
    return {
        "name": "C_shrinkage_penalty_quantified",
        "plain_f5_shrinkage_events": plain_events,
        "no_shrinkage_variant_events": ns_events,
        "efficiency_plain_f5": round(ep, 4),
        "efficiency_no_shrinkage": round(en, 4),
        "efficiency_lost_to_shrinkage": f"{(1 - ep / en):.1%}",
        "rate_plain_f5": round(rp, 4),
        "rate_no_shrinkage": round(rn, 4),
        "rate_lost_to_shrinkage": f"{(1 - rp / rn):.1%}",
        "pass": ok,
        "note": ("A shrinkage event spends a change and carries no bits, so "
                 "the loss is payload, not just a histogram artefact. Real "
                 "nsF5 uses wet paper codes; this variant increments |1| to "
                 "|2| instead, which is simpler and gives up some capacity."),
    }


def criterion_d_jsteg(coeff_sets: List[np.ndarray]) -> Dict:
    """Jsteg equalises the pairs it touches and skips the pair {0, 1}."""
    touched_gaps_before, touched_gaps_after = [], []
    skipped_ratio_before, skipped_ratio_after = [], []

    for i, coeffs in enumerate(coeff_sets):
        before = E.coefficient_histogram(coeffs)
        stego = E.jsteg(coeffs, rate=0.9, seed=400 + i).stego
        after = E.coefficient_histogram(stego)

        # Pair (2, 3) is embedded into; pair (0, 1) is skipped by the rule.
        def gap(h):
            a, b = float(h[10]), float(h[11])       # values 2 and 3
            return abs(a - b) / (a + b) if (a + b) else 0.0

        def zero_one(h):
            a, b = float(h[8]), float(h[9])         # values 0 and 1
            return a / b if b else 0.0

        touched_gaps_before.append(gap(before))
        touched_gaps_after.append(gap(after))
        skipped_ratio_before.append(zero_one(before))
        skipped_ratio_after.append(zero_one(after))

    tb, ta = float(np.mean(touched_gaps_before)), float(np.mean(touched_gaps_after))
    sb, sa = float(np.mean(skipped_ratio_before)), float(np.mean(skipped_ratio_after))
    skipped_drift = abs(sa - sb) / sb if sb else 1.0

    return {
        "name": "D_jsteg_equalises_only_what_it_touches",
        "pair_2_3_imbalance_before": round(tb, 4),
        "pair_2_3_imbalance_after": round(ta, 4),
        "zero_over_one_ratio_before": round(sb, 3),
        "zero_over_one_ratio_after": round(sa, 3),
        "skipped_pair_drift": round(skipped_drift, 4),
        "pass": ta < tb and skipped_drift < 0.05,
        "note": ("The embedded pair flattens; the skipped pair does not. "
                 "That contrast is the chi-square attack's whole basis."),
    }


def main() -> int:
    coeff_sets = load_coefficients()
    if not coeff_sets:
        print("SKIP: no baseline-sequential carriers could be decoded.")
        return 0

    results = [
        criterion_a_efficiency(coeff_sets),
        criterion_b_rate(coeff_sets),
        criterion_c_shrinkage(coeff_sets),
        criterion_d_jsteg(coeff_sets),
    ]

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "G2.json").write_text(json.dumps(results, indent=2) + "\n")

    print("=" * 70)
    print(f"Gate G2 -- classical embedding, {len(coeff_sets)} JPEG carriers")
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
            if key == "rows":
                for row in value:
                    print(f"        k={row['k']}  theory={row['theory']:<8} "
                          f"measured={row['measured']:<8} "
                          f"err={row['relative_error']:.4%}")
            else:
                print(f"        {key}: {value}")
        if "note" in r:
            print(f"        -> {r['note']}")
    print("=" * 70)
    print("GATE G2:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
