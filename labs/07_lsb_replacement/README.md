# Lab 07 -- LSB replacement, and the E3 ceiling

| | |
|---|---|
| Domain | spatial |
| Algorithm | lsb-replacement |
| Detectors | `rs_analysis`, `weighted_stego` |
| Measured FPR | 0/40 on matched-source clean covers; 25% on mismatched |
| Evidence ceiling | E3 (E4 only when embedding is sequential) |

## What changes here

Every A-group lab produced the payload. This one produces a *number*.

RS analysis and Weighted Stego estimate the relative payload. They establish
that something is embedded and roughly how much, and neither yields a byte
of it without the embedding path. So the finding stops at E3: domain
identified, existence confirmed, payload not in hand.

That ceiling is the honest one. When embedding is sequential from the first
sample the payload is trivially recoverable and the finding climbs to E4;
when positions come from a keyed permutation, it does not, and the report
should say so rather than implying a partial extraction is imminent.

## Thresholds

`RS_THRESHOLD = 0.344` and `WS_THRESHOLD = 0.376` are not chosen by taste.
They are gate G4's measured operating points: the thresholds that give 95%
true positives against 0.5 bpp replacement, at which both detectors show
zero false positives on 80 matched-source clean covers.

## Detection performance

From gate G4, AUC over 80 covers:

| relative payload | RS analysis | Weighted Stego |
|---|---|---|
| 0.05 | 0.621 | 0.594 |
| 0.10 | 0.735 | 0.840 |
| 0.25 | 0.927 | 1.000 |
| 0.50 | 1.000 | 1.000 |

Weighted Stego is also quantitative: mean absolute error against known
payloads stays between 0.031 and 0.044 across all rates.

## The false-positive test that failed first

The zero-false-positive test failed on its first run at 25%. The detector
was fine; the *baseline* was drawn from four synthetic image families
including flat and gradient images, where local variation is near zero and
both estimators become unstable.

Same detector, same threshold, different baseline source:

| detector | matched source | mixed source |
|---|---|---|
| RS analysis | 0/60 | 15/60 |
| Weighted Stego | 0/60 | 15/60 |

That is cover source mismatch, measured. It is why `measure_baseline` takes
a `kinds` argument and why the evidence ladder says *same* source rather
than similar source.

## Reproduce

```bash
python3 -m pytest tests/test_labs_b.py -q
python3 gates/g4_statistical.py --n 80
```

## What it teaches

A statistical verdict is a threshold applied to an estimate, and a threshold
without a same-source baseline is a number with no meaning attached.

---

[Chinese version](README_zh.md)
