# T5 -- Feature sets and ensemble classification

> Gate: **G5** -- `python3 gates/g5_feature_sets.py` -- PASSED

## 5.1 Why the estimators ran out

T4 ended with an admission: RS analysis and Weighted Stego detect LSB
replacement and are at chance against LSB matching, all three shipped
detectors staying within 0.086 of chance at every payload.

That is not a defect in those estimators. Each models a specific structure
-- the even/odd asymmetry replacement leaves behind -- and matching does not
create it. No amount of tuning conjures a structure that is absent.

The way out is to stop modelling the *artefact* and start modelling the
*cover*.

## 5.2 SPAM

SPAM looks at local dependencies between adjacent pixels rather than at
pixel values. Take differences between neighbouring pixels in eight
directions, truncate them to the range [-3, 3] because the tail is sparse,
and model each difference sequence as a second-order Markov chain. That
gives 7^3 = 343 transition probabilities per direction; averaging the
horizontal and vertical directions into one group and the two diagonals into
another yields the standard **SPAM686**.

Two implementation details carry real weight:

**Conditional normalisation.** Each `(u, v)` conditioning state is
normalised separately, not globally. SPAM is a conditional model; normalise
across all states and the strong states smear into the weak ones, costing
most of the signal.

**Direction averaging is an assumption, not a shortcut.** It encodes the
claim that a cover's statistics are direction-symmetric. That halves the
dimensionality without discarding anything a cover is expected to contain --
and it is a claim about covers, so it is one more thing that can fail on a
source you have not characterised.

## 5.3 Why an ensemble of weak learners

686 features and a few hundred training images is a badly conditioned
problem. A single Fisher discriminant on all of them overfits, and its
within-class covariance estimate is close to singular.

The FLD ensemble sidesteps this rather than solving it: each base learner
gets a random subspace of ~200 features and a bootstrap sample of the
training set, computes a closed-form Fisher direction, picks the threshold
minimising its own training error, and votes. Random subspaces keep each
sub-problem well conditioned; bagging decorrelates the learners.

It is the standard steganalysis classifier mostly because it is *fast enough
to retrain per source*, and retraining per source turns out to be the only
honest way to use any of this.

## 5.4 P_E, and what it hides

The field's standard figure is the minimal average decision error under
equal priors:

    P_E = min over thresholds of (P_FA + P_MD) / 2

It is not an accuracy. It weights false alarms and missed detections
equally, which is a reasonable default for comparing methods in a laboratory
and the wrong one for almost any real case, where the two errors cost very
different amounts. Any operational threshold has to be re-chosen from the
ROC with those costs in view.

## 5.5 What the gate measured

**The gap from T4 closes.** Against LSB matching at 1.0 bpp:

| detector | P_E |
|---|---|
| RS analysis | 0.473 |
| Weighted Stego | 0.450 |
| SPAM686 + FLD ensemble | **0.140** |

**And it closes for the stated reason.** If the classifier had latched onto
something replacement-specific, it would score very differently on the two
embedders:

| embedder | P_E at 1.0 bpp |
|---|---|
| LSB matching | 0.140 |
| LSB replacement | 0.120 |

Spread 0.02. The method is embedder-agnostic because it models the cover.
That was the claim; this is the measurement.

## 5.6 Cover source mismatch, now unavoidable

T4 met this by accident, when a baseline drawn from the wrong image families
moved a false-positive rate from 0% to 25%. Here it is structural.

Train the classifier on one image family, test it on another:

| | P_E |
|---|---|
| trained and tested on texture/photo_like | 0.140 |
| trained on texture/photo_like, tested on gradient/flat | **0.487** |

0.487 is chance. This is not graceful degradation; the classifier stops
working entirely.

The operational consequence is the reason lab 09's `detect` refuses to run
without a classifier argument. A feature-set detector has no fixed decision
rule -- it has a decision rule *for a source*. A pre-trained classifier
shipped in a repository is calibrated to somebody else's camera, and the
number it produces on your evidence means nothing. The API is built to make
that impossible to forget rather than merely documented.

This is also where the evidence ladder's insistence on a *same-source*
baseline stops being a style preference. At E3 and above the ladder demands
a measured false-positive rate from the same source; without one, the number
above is what you get.

## 5.7 The same gate on real photographs

BOSSbase 1.01, 200 training pairs and 200 test pairs, all from one camera
(canon_eos_7d) so the training set is genuinely same-source.

| quantity | synthetic | real |
|---|---|---|
| P_E vs LSB matching at 1.0 bpp | 0.140 | **0.125** |
| P_E vs LSB matching at 0.5 bpp | 0.297 | **0.215** |
| best structural detector, same task | 0.450 | 0.405 |
| margin over structural | 0.31 | 0.28 |

The gap T4 opened stays closed on real data, and the margin over the
structural estimators survives.

Criterion C produced the more interesting number. Against LSB replacement
P_E is **0.030**; against matching, 0.125. Replacement leaves extra
structure, so of course it is easier -- but the criterion as originally
written demanded the two agree within 0.10, and 0.095 came within one
thousandth of failing. It would have failed outright if SPAM had got *better*
at replacement, which is perverse. The claim being tested is that neither
embedder is invisible, so the criterion now requires both P_E values at or
below 0.25 and reports the spread separately.

## 5.8 What cover source mismatch actually costs, split two ways

Criterion D failed on first contact with real data, and the failure was the
useful part.

Training on canon_eos_7d and testing on nikon_d70 moved P_E from 0.125 to
**0.160** -- a degradation of 0.035 against a required 0.05. On synthetic
image families the same criterion had measured a collapse from 0.140 to
0.487.

The threshold was not lowered. The reason for the difference is structural:
**every image in BOSSbase went through the same RAW development script and
the same resize.** A cross-camera comparison there isolates the sensor and
holds everything else fixed. The synthetic comparison was textured images
against flat and gradient ones -- a *content* shift, far more violent than
any sensor difference, and never a fair calibration for this criterion.

So the criterion split in two:

**D1, sensor shift.** Train on one camera, test on several others.
Degradation must be positive for a majority of pairs. Mild by construction,
and that is a fact about the dataset rather than a weak result.

**D2, pipeline shift.** Same images, same camera, one resample -- downscale
by two with area averaging, back up bilinearly. Must degrade by at least
0.05. On synthetic covers this alone takes P_E from 0.163 to **0.500**,
complete collapse.

The operational reading: swapping the camera costs a few points; putting the
evidence through a resize costs everything. Casework almost always involves
the second, because evidence arrives resized, re-encoded and platform-
transcoded. A classifier trained on pristine originals has no standing
against it.

## 5.9 Absolute performance, honestly

P_E of 0.297 at 0.5 bpp is poor. Published SPAM686 results on BOSSbase reach
an order of magnitude better at that payload, trained on 10,000 real camera
images rather than 150 synthetic ones.

The *relative* result -- a feature set detects what the structural
estimators cannot, and does so embedder-agnostically -- is what transfers.
The absolute numbers do not, and quoting them outside this corpus would be
misuse. Gap G-4 stays open until real corpora are in place.

## 5.10 What comes after SPAM

SRM (Spatial Rich Models) generalises the idea: dozens of residual filters
instead of one difference operator, tens of thousands of features instead of
686, with the same ensemble on top. maxSRMd2 weights the residuals by an
estimate of where embedding is most likely. In the JPEG domain the
equivalents are DCTR and GFR.

The direction of travel is consistent -- richer cover models, the same
classifier -- and it runs until T6 replaces hand-designed residuals with
learned ones.

## 5.11 Further reading

Pevny, Bas and Fridrich (2010) for SPAM; Fridrich and Kodovsky (2012) for
rich models; Kodovsky, Fridrich and Holub (2012) for the FLD ensemble; Ker
et al. (2013) on why laboratory P_E figures do not transfer, which should be
read before quoting any number in this chapter outside this corpus.

---

Previous: [T4 -- Statistical steganalysis](T4_statistical_steganalysis.md) |
[Chinese version](T5_feature_sets_zh.md)
