# Lab 09 -- Feature-based detection, and a detector that must be trained

| | |
|---|---|
| Domain | spatial |
| Algorithm | embedder-agnostic |
| Detector | `spam686_fld_ensemble` |
| P_E on LSB matching at 1.0 bpp | 0.140 |
| P_E under source mismatch | 0.487 (chance) |
| Evidence ceiling | E3 |

## What this lab closes

Lab 08 shipped no detector: RS analysis, Weighted Stego and chi-square all
sat within 0.086 of chance against LSB matching. This is where that changes.

SPAM stops modelling the embedder's artefact and models the *cover* instead
-- specifically the second-order dependencies between adjacent pixel
differences. Any embedding perturbs those dependencies, whether or not it
respects value pairs.

| detector | P_E vs LSB matching at 1.0 bpp |
|---|---|
| RS analysis | 0.473 |
| Weighted Stego | 0.450 |
| SPAM686 + FLD ensemble | **0.140** |

## The evidence that it works for the stated reason

If the classifier had latched onto something replacement-specific, it would
score very differently on the two embedders. It does not:

| embedder | P_E at 1.0 bpp |
|---|---|
| LSB matching | 0.140 |
| LSB replacement | 0.120 |

Spread: 0.02. The method is embedder-agnostic because it models the cover,
which is the claim, now measured.

## Why `detect` refuses to run untrained

Every earlier lab exposed a detector that was a function. This one cannot
be, and the API says so: `detect` requires a `classifier` and returns E0
without one.

A feature-set classifier has no fixed decision rule. It has a decision rule
*for a source*. Gate G5 criterion D measured the cost of ignoring that:

| | P_E |
|---|---|
| trained and tested on the same families | 0.140 |
| trained on texture/photo_like, tested on gradient/flat | 0.487 |

That is not graceful degradation. It is the classifier ceasing to work. A
pre-trained detector shipped in a repository is calibrated to somebody
else's source, and the number it produces on your evidence means nothing.

## Absolute performance, honestly

P_E of 0.297 at 0.5 bpp is poor. Published SPAM686 results on BOSSbase reach
an order of magnitude better at that payload, trained on 10,000 real camera
images rather than 150 synthetic ones.

The *relative* result -- a feature set detects what the structural
estimators cannot -- is what transfers. The absolute numbers do not, and
quoting them outside this corpus would be misuse.

## Reproduce

```bash
python3 gates/g5_feature_sets.py --n 300
python3 -m pytest tests/test_labs_c.py -q
```

## What it teaches

The step from an estimator to a classifier buys generality and costs
portability. Everything the evidence ladder says about same-source baselines
becomes load-bearing here rather than advisory.

---

[Chinese version](README_zh.md)
