# Lab 08 -- LSB matching: a lab with no working detector

| | |
|---|---|
| Domain | spatial |
| Algorithm | lsb-matching |
| Detectors | none that work |
| Measured deviation from chance | 0.086 worst case, gate G4 |
| Evidence ceiling | E0 |

## This lab ships no detector, and that is the content

LSB replacement can only ever move a value between the two members of one
pair. That constraint is a structure, and RS analysis, Sample Pair Analysis
and Weighted Stego are all estimators of how far it has been eroded.

LSB matching adds or subtracts one at random. The change to the embedder is
one line. The structure never forms, and the entire family loses its signal
at once.

## How completely

Gate G4, 80 covers, five relative payloads:

| detector | 0.05 | 0.10 | 0.25 | 0.50 | 1.00 |
|---|---|---|---|---|---|
| RS analysis | 0.531 | 0.532 | 0.511 | 0.518 | 0.586 |
| Weighted Stego | 0.514 | 0.516 | 0.550 | 0.532 | 0.573 |
| chi-square | 0.517 | 0.485 | 0.505 | 0.450 | 0.445 |

Compare lab 07, where Weighted Stego reaches AUC 1.000 at 0.25 bpp.

## Why `detect` returns E0

Reporting E1 on every image because a stronger algorithm might be present
would be a detector with a 100% false-positive rate wearing a disclaimer.
There is nothing honest to report, so nothing is reported.

## What was tried and did not work

Calibrated HCF centre of mass (Ker, 2005) is the classical answer to "so
what *does* detect this?". Measured AUC on this corpus: 0.482 at 0.25 bpp.
Chance.

The obvious explanation -- that these covers carry more high-frequency noise
than a +/-1 perturbation -- was tested by sweeping cover noise from
sigma=0.5 to sigma=6.0 and is **falsified**: AUC stayed within [0.505, 0.533]
throughout. See `calibrated_hcf_com_UNVALIDATED` and gap G-12.

## Reproduce

```bash
python3 -m pytest tests/test_labs_b.py -q
```

The test asserts the *failure* as a measured quantity. If a structural
detector ever starts working here, it goes red and demands an explanation --
which is correct, because the likeliest cause is a broken embedder, not a
breakthrough.

## What it teaches

The distance between "we have a detector for LSB steganography" and "we have
a detector for LSB replacement" is one line of embedder code. T5's feature
sets and ensemble classifiers are where this changes, and knowing why they
were necessary is worth more than being handed a detector that works.

---

[Chinese version](README_zh.md)
