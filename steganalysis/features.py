"""Feature sets and ensemble classification -- the T5 machinery.

T4 ended with an admission: RS analysis and Weighted Stego detect LSB
replacement and are at chance against LSB matching. That is not a defect in
those estimators. They model a specific structure, matching does not create
it, and no amount of tuning conjures a structure that is absent.

The way out is to stop modelling one artefact and start modelling the cover
instead. SPAM does this by looking at *local dependencies* between adjacent
pixels rather than at pixel values. Embedding of any kind perturbs those
dependencies, whether or not it respects value pairs -- so a detector built
on them does not care which of the two embedders produced the change.

The price is that the answer is no longer a formula. It is a classifier,
which needs training data, which means everything now depends on whether the
training set and the evidence came from the same source. T4 met that problem
by accident; here it is unavoidable.

SPAM: Pevny, Bas and Fridrich (2010).
FLD ensemble: Kodovsky, Fridrich and Holub (2012).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

# Truncation threshold. Differences beyond +/-T are clipped, because the tail
# is sparse and would contribute mostly noise. T=3 with second-order chains
# gives 7^3 = 343 bins per direction group, the standard SPAM686.
T = 3
BINS = 2 * T + 1


def _differences(img: np.ndarray) -> dict:
    """Adjacent-pixel differences in all eight directions."""
    a = img.astype(np.int16)
    return {
        "->": a[:, :-1] - a[:, 1:],
        "<-": a[:, 1:] - a[:, :-1],
        "|v": a[:-1, :] - a[1:, :],
        "|^": a[1:, :] - a[:-1, :],
        "\\v": a[:-1, :-1] - a[1:, 1:],
        "\\^": a[1:, 1:] - a[:-1, :-1],
        "/v": a[:-1, 1:] - a[1:, :-1],
        "/^": a[1:, :-1] - a[:-1, 1:],
    }


def _markov2(diff: np.ndarray, axis: int) -> np.ndarray:
    """Second-order transition probabilities along one axis, truncated to +/-T."""
    d = np.clip(diff, -T, T) + T
    if axis == 0:
        u, v, w = d[:-2, :], d[1:-1, :], d[2:, :]
    else:
        u, v, w = d[:, :-2], d[:, 1:-1], d[:, 2:]

    idx = (u * BINS * BINS + v * BINS + w).reshape(-1)
    counts = np.bincount(idx, minlength=BINS ** 3).astype(np.float64)

    # Normalise per (u, v) conditioning state, not globally: SPAM is a
    # conditional model. Normalising globally would smear the strong states
    # into the weak ones and cost most of the signal.
    counts = counts.reshape(BINS * BINS, BINS)
    totals = counts.sum(axis=1, keepdims=True)
    totals[totals == 0] = 1.0
    return (counts / totals).reshape(-1)


def spam686(img: np.ndarray) -> np.ndarray:
    """The 686-dimensional second-order SPAM feature vector.

    Horizontal and vertical directions are averaged into one 343-vector and
    the two diagonals into another. The averaging is not a shortcut: it
    encodes the assumption that a cover's statistics are direction-symmetric,
    which halves the dimensionality without discarding anything a cover is
    expected to contain.
    """
    if img.ndim == 3:
        img = img[..., 0]
    d = _differences(img)

    horizontal_vertical = [
        _markov2(d["->"], 1), _markov2(d["<-"], 1),
        _markov2(d["|v"], 0), _markov2(d["|^"], 0),
    ]
    diagonal = [
        _markov2(d["\\v"], 1), _markov2(d["\\^"], 1),
        _markov2(d["/v"], 1), _markov2(d["/^"], 1),
    ]

    f1 = np.mean(horizontal_vertical, axis=0)
    f2 = np.mean(diagonal, axis=0)
    return np.concatenate([f1, f2])


FEATURE_DIM = 2 * BINS ** 3


# --------------------------------------------------------------------------
# FLD ensemble
# --------------------------------------------------------------------------

@dataclass
class _BaseLearner:
    features: np.ndarray      # indices of the random subspace
    w: np.ndarray             # Fisher direction
    threshold: float


@dataclass
class FldEnsemble:
    """Ensemble of Fisher linear discriminants on random feature subspaces.

    Why an ensemble of weak, cheap learners rather than one strong one: the
    feature space is high-dimensional and the training set is small, so a
    single discriminant on all 686 features overfits badly and its covariance
    estimate is singular. Random subspaces keep each learner's problem
    well-conditioned; bagging decorrelates them; majority vote does the rest.

    This is the standard steganalysis classifier precisely because it is
    fast enough to retrain per source, and retraining per source is the only
    honest way to use it.
    """

    n_learners: int = 40
    d_sub: int = 200
    seed: int = 0
    learners: List[_BaseLearner] = field(default_factory=list)
    _mu: Optional[np.ndarray] = None
    _sigma: Optional[np.ndarray] = None

    def _standardise(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        if fit:
            self._mu = X.mean(axis=0)
            self._sigma = X.std(axis=0)
            self._sigma[self._sigma < 1e-12] = 1.0
        return (X - self._mu) / self._sigma

    def fit(self, cover: np.ndarray, stego: np.ndarray) -> "FldEnsemble":
        X = np.vstack([cover, stego])
        self._standardise(X, fit=True)
        c = self._standardise(cover)
        s = self._standardise(stego)

        rng = np.random.default_rng(self.seed)
        n_features = c.shape[1]
        d_sub = min(self.d_sub, n_features)
        self.learners = []

        for _ in range(self.n_learners):
            cols = rng.choice(n_features, size=d_sub, replace=False)
            ci = rng.choice(len(c), size=len(c), replace=True)
            si = rng.choice(len(s), size=len(s), replace=True)
            cc, ss = c[np.ix_(ci, cols)], s[np.ix_(si, cols)]

            mu_c, mu_s = cc.mean(axis=0), ss.mean(axis=0)
            within = np.cov(cc, rowvar=False) + np.cov(ss, rowvar=False)
            within += np.eye(d_sub) * 1e-6 * np.trace(within) / d_sub

            try:
                w = np.linalg.solve(within, mu_s - mu_c)
            except np.linalg.LinAlgError:
                continue

            proj_c = cc @ w
            proj_s = ss @ w
            # Threshold minimising the training error, found by scanning the
            # midpoints of the merged projections rather than assuming
            # Gaussian equal-variance classes.
            candidates = np.unique(np.concatenate([proj_c, proj_s]))
            if candidates.size > 400:
                candidates = np.quantile(candidates, np.linspace(0, 1, 400))
            errors = [(np.count_nonzero(proj_c >= t) + np.count_nonzero(proj_s < t), t)
                      for t in candidates]
            _, best = min(errors)
            self.learners.append(_BaseLearner(cols, w, float(best)))

        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        """Fraction of base learners voting 'stego'. In [0, 1]."""
        Z = self._standardise(X)
        votes = np.zeros(len(X))
        for lr in self.learners:
            votes += (Z[:, lr.features] @ lr.w >= lr.threshold).astype(np.float64)
        return votes / max(len(self.learners), 1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.decision_function(X) >= 0.5).astype(np.int8)


def min_error_probability(cover_scores: np.ndarray,
                          stego_scores: np.ndarray) -> Tuple[float, float]:
    """P_E, the minimal average decision error under equal priors.

    P_E = min over thresholds of (P_FA + P_MD) / 2

    This is the field's standard figure and it is *not* an accuracy. It
    weights false alarms and missed detections equally, which is the right
    default for a laboratory comparison and the wrong one for a real case --
    where the two errors almost never cost the same. Any operational
    threshold has to be re-chosen from the ROC.
    """
    thresholds = np.unique(np.concatenate([cover_scores, stego_scores]))
    best = 1.0
    best_t = 0.5
    for t in thresholds:
        pfa = np.count_nonzero(cover_scores >= t) / len(cover_scores)
        pmd = np.count_nonzero(stego_scores < t) / len(stego_scores)
        pe = (pfa + pmd) / 2.0
        if pe < best:
            best, best_t = pe, float(t)
    return float(best), best_t
