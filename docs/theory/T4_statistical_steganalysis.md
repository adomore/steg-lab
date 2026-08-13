# T4 -- Statistical steganalysis

> Gate: **G4** -- `python3 gates/g4_statistical.py` -- PASSED

## 4.1 The shift this chapter makes

Everything in the A group produced a payload. From here the detectors
produce a *number*, and a number needs a threshold, and a threshold needs a
baseline. This is where the evidence ladder stops being a formality.

## 4.2 The chi-square attack

LSB replacement drives the counts of 2i and 2i+1 towards their common mean.
The test compares observed frequencies against that mean, and reports a
p-value near 1 when the histogram looks flattened -- the opposite of the
usual reading of a p-value, which catches people out.

It is strongest against sequential embedding from the first sample, because
a randomly spread payload dilutes the effect across the whole image.

**On this corpus it is close to useless, and the gate reports that.** Over
80 clean covers the mean p-value is 0.944 and 64 of the 80 exceed 0.9. At
the threshold that gives 95% true positives on 0.5 bpp replacement, its
false-positive rate is **27/80 = 33.8%**.

The cause is the corpus, not the method: these synthetic covers already have
near-equal pair counts, so they look flattened before anything is embedded.
That is direct evidence for the claim that synthetic covers are inadequate
for statistical work -- the reason every gate from here needs BOSSbase.

## 4.3 RS analysis

Groups of adjacent pixels are classified by whether a masked LSB flip
increases their local variation (**Regular**) or decreases it (**Singular**).
In a natural image R > S. Replacement pushes the two together; the *shifted*
flipping function F-1 pushes them apart. Measuring both at two embedding
points and fitting a quadratic recovers the payload.

## 4.4 Weighted Stego

    p = (2/n) * sum_i w_i * (s_i - pred_i) * (s_i - F1(s_i))

The second factor is +1 for odd samples and -1 for even ones, so the sum
measures whether the residual between a sample and its locally predicted
value correlates with the sample's parity. In a clean image it does not;
under replacement it does, in proportion to the payload.

WS is the most interpretable of the three: it is a weighted average, so a
poor predictor degrades it gracefully rather than making it lie. Weighting
down pixels in noisy neighbourhoods is the standard first refinement and is
what this implementation uses.

## 4.5 What the gate measured

Detection AUC over 80 covers, five relative payloads, two embedders.

**LSB replacement:**

| detector | 0.05 | 0.10 | 0.25 | 0.50 | 1.00 |
|---|---|---|---|---|---|
| RS analysis | 0.621 | 0.735 | 0.927 | 1.000 | 0.984 |
| Weighted Stego | 0.594 | 0.840 | 1.000 | 1.000 | 1.000 |
| chi-square | 0.580 | 0.616 | 0.729 | 0.871 | 0.958 |

**LSB matching:**

| detector | 0.05 | 0.10 | 0.25 | 0.50 | 1.00 |
|---|---|---|---|---|---|
| RS analysis | 0.531 | 0.532 | 0.511 | 0.518 | 0.586 |
| Weighted Stego | 0.514 | 0.516 | 0.550 | 0.532 | 0.573 |
| chi-square | 0.517 | 0.485 | 0.505 | 0.450 | 0.445 |

Worst deviation from chance across the whole matching table: **0.086**.

This is a **required criterion** of the gate. A course that only
demonstrates successes trains an analyst to expect them. The single most
useful fact in this chapter is that a one-line change to the embedder costs
the entire structural family its signal at once, and it is asserted as a
measured quantity so that a future regression cannot quietly erase it.

Weighted Stego is also a quantitative estimator, and its mean absolute error
against known payloads stays between 0.031 and 0.044 across all five rates.
That is what lets a report say how much was hidden, not merely that
something was.

## 4.6 The same gate on real photographs

Re-run against BOSSbase 1.01, 200 covers centre-cropped to 256px. Cropping
rather than resizing, because resampling filters exactly the high-frequency
content these detectors measure.

**LSB replacement, detection AUC:**

| detector | 0.05 | 0.10 | 0.25 | 0.50 | 1.00 |
|---|---|---|---|---|---|
| RS analysis | 0.724 | 0.863 | 0.984 | 1.000 | 0.994 |
| Weighted Stego | 0.882 | 0.977 | 0.999 | 1.000 | 1.000 |
| chi-square | 0.527 | 0.545 | 0.606 | 0.737 | 0.990 |

Compare the synthetic table above. At 0.05 bpp -- the payload that actually
matters, because anything larger is easy -- Weighted Stego moves from **0.594
to 0.882**, and RS from 0.621 to 0.724. Real sensor noise is what these
estimators were designed to work in, and the synthetic corpus was quietly
costing them most of their low-payload sensitivity.

**LSB matching** stays at chance, worst deviation 0.1124 against a tolerance
of 0.15. The required failure reproduces on real data, which is the more
important half of the result. One detail: chi-square reaches 0.612 at 1.0 bpp,
the largest single value in the table, so a saturated matching payload is not
completely invisible to a histogram test.

**Weighted Stego's quantitative accuracy** improves too: mean absolute error
0.023 / 0.028 / 0.038 / 0.045 / 0.015 across the five payloads.

**And chi-square becomes a usable detector.** On synthetic covers its clean
mean p-value was 0.944, 64 of 80 exceeded 0.9, and it had no usable operating
point at any threshold. On BOSSbase the clean mean is **0.129** with 18 of 200
above 0.9, and it reaches AUC 0.990 at full payload. RS and WS both report
**0/200 false positives** at their 95%-TPR thresholds.

That contrast is the whole argument for a real corpus, now measured rather
than asserted.

A bug fell out of the re-run. The false-positive baseline picked its
threshold with `quantile(stego, 1 - target)`, which is fine for spread-out
scores and wrong when they pile up on a boundary: most real covers score
exactly 0.0 under chi-square, so the threshold came out at 0.0, every clean
cover satisfied `>= 0.0`, and the gate reported "FPR = 1.000 at threshold
0.0" as though it were a measurement. It now scans thresholds for the minimum
achievable FPR and says plainly when a detector has no operating point at
all -- which is a result about the detector, not a false-positive rate.

## 4.7 Cover source mismatch, found by accident

The lab 07 false-positive test failed on first run at 25%. The cause was not
the detector.

The baseline was drawn from a mixed set: four synthetic image families,
including flat and gradient images where local variation is nearly zero and
both estimators become unstable. Restricting the baseline to the same
families the carrier came from gives this:

| detector | matched source | mixed source |
|---|---|---|
| RS analysis | 0/60 (0.0%) | 15/60 (25.0%) |
| Weighted Stego | 0/60 (0.0%) | 15/60 (25.0%) |

Same detector, same threshold, same carriers. **The only difference is which
covers the baseline was drawn from, and it moves the false-positive rate
from nothing to a quarter.**

This is cover source mismatch, which T5 treats as a central problem and
which is normally taught in the abstract. It was found here by accident,
which is the usual way. It is also the concrete reason the evidence ladder
insists a baseline come from the *same* source rather than from a source
that seems similar: "similar" is doing all the work, and it is not doing it
reliably.

## 4.8 What this repository cannot do

Two detectors were written for this chapter and neither ships.

**Sample Pair Analysis.** The theory is sound and belongs in any treatment
of this material. Two candidate set partitions were implemented and neither
tracked ground truth -- estimates moved in the wrong direction against known
payloads. Rather than ship an estimator that produces confident numbers from
an unverified formula, it is kept in the module, renamed
`sample_pair_analysis_UNVALIDATED`, and excluded from the registry. Gap
G-11; P2 derives it from the source paper with each step checked against
measured transition counts.

**Calibrated HCF centre of mass.** This is the classical answer to "so what
*does* detect LSB matching?". Measured AUC on this corpus: 0.482 at 0.25 bpp,
0.472 at 0.5 bpp. Chance.

The obvious explanation -- that these covers carry more high-frequency noise
than a +/-1 perturbation -- was tested by sweeping cover noise from
sigma=0.5 to sigma=6.0 and is **falsified**: AUC stayed within [0.505, 0.533]
while cover local standard deviation moved only from 5.66 to 7.53, because
the upsampled base dominates it. The remaining candidates are that this is
the weak one-dimensional variant where Ker's method uses the
two-dimensional adjacency histogram, or that the corpus lacks the
natural-image statistics calibration assumes. Distinguishing them needs
BOSSbase. Gap G-12.

So the honest position at P1: **this repository detects LSB replacement and
cannot detect LSB matching.** T5's feature sets and ensemble classifiers are
where that changes, and knowing why they were necessary is worth more than
having been handed a detector that works.

## 4.9 Further reading

Westfeld and Pfitzmann (1999) for chi-square; Fridrich, Goljan and Du (2001)
for RS; Dumitrescu, Wu and Wang (2003) for SPA; Fridrich and Goljan (2004)
for WS; Ker (2005) for calibrated HCF-COM; Ker et al. (2013) on why
laboratory results do not transfer, required before quoting any of the
numbers above outside this corpus.

---

Previous: [T2 -- Classical embedding algorithms](T2_classical_algorithms.md) |
[Chinese version](T4_statistical_steganalysis_zh.md)
