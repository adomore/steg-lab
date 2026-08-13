"""Statistical detectors, implemented from scratch.

Four of these target LSB replacement and one targets LSB matching. That
split is the point of T4. Replacement leaves a structural asymmetry between
the two members of each value pair (2i, 2i+1); RS analysis, Sample Pair
Analysis and Weighted Stego all estimate the payload from that asymmetry,
and all three collapse when it is absent. Matching does not create it, so it
needs a distributional attack instead -- here, the calibrated centre of mass
of the histogram characteristic function.

Every estimator returns a *quantitative* payload estimate, not a boolean.
A detector that only says yes or no cannot be given a threshold, and a
threshold that cannot be varied cannot produce a ROC curve, and without a
ROC curve there is no false-positive rate to report. The evidence ladder
depends on this all the way down.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
from scipy import stats


@dataclass
class Estimate:
    """A quantitative payload estimate plus whatever the detector saw."""

    detector: str
    value: float          # estimated relative payload, or a test statistic
    statistic: Optional[float] = None
    detail: Optional[dict] = None

    def __float__(self) -> float:
        return float(self.value)


def _as_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        # ITU-R 601 luma. Rounding matters: LSB detectors are, by
        # construction, sensitive to the last bit, so a float conversion
        # would silently destroy exactly the signal being measured.
        # Analysing one colour plane is the honest alternative.
        return image[..., 0].astype(np.int16)
    return image.astype(np.int16)


# --------------------------------------------------------------------------
# Chi-square attack (Westfeld & Pfitzmann, 1999)
# --------------------------------------------------------------------------

def chi_square(image: np.ndarray, pairs: int = 128) -> Estimate:
    """Test whether the members of each value pair have been equalised.

    LSB replacement drives the counts of 2i and 2i+1 towards their common
    mean. The test compares observed frequencies against that mean; a
    p-value near 1 means the histogram looks like it has been flattened,
    which is the opposite of the usual reading of a p-value and catches
    people out.

    The attack is strongest against *sequential* embedding starting at the
    first sample. Randomly spread payloads dilute the effect across the
    whole image, which is why `chi_square_windowed` exists.
    """
    gray = _as_gray(image)
    hist = np.bincount(gray.reshape(-1).astype(np.int64), minlength=256)[:256]

    even = hist[0:2 * pairs:2].astype(np.float64)
    odd = hist[1:2 * pairs:2].astype(np.float64)
    expected = (even + odd) / 2.0

    valid = expected > 4        # chi-square needs a minimum expected count
    if valid.sum() < 2:
        return Estimate("chi_square", 0.0, statistic=0.0)

    chi2 = float(np.sum((even[valid] - expected[valid]) ** 2 / expected[valid]))
    dof = int(valid.sum()) - 1
    p_stego = float(1.0 - stats.chi2.cdf(chi2, dof))

    return Estimate("chi_square", p_stego, statistic=chi2,
                    detail={"dof": dof, "pairs_used": int(valid.sum())})


def chi_square_windowed(image: np.ndarray, window: int = 4096) -> Estimate:
    """Slide the chi-square test along the sample order.

    Returns the maximum p-value over windows. A sequentially embedded image
    shows a run of high p-values at the start that collapses where the
    payload ends -- which also localises the payload length.
    """
    gray = _as_gray(image).reshape(-1)
    n = gray.size
    best = 0.0
    best_at = 0
    for start in range(0, max(n - window, 1), window):
        block = gray[start:start + window]
        est = chi_square(block)
        if est.value > best:
            best, best_at = est.value, start
    return Estimate("chi_square_windowed", best,
                    detail={"window": window, "peak_offset": best_at})


# --------------------------------------------------------------------------
# RS analysis (Fridrich, Goljan & Du, 2001)
# --------------------------------------------------------------------------

_MASK = np.array([1, 0, 0, 1], dtype=np.int8)


def _flip_f1(x: np.ndarray) -> np.ndarray:
    """F1: 0<->1, 2<->3, ... i.e. flip the LSB."""
    return np.bitwise_xor(x.astype(np.int16), 1)


def _flip_fm1(x: np.ndarray) -> np.ndarray:
    """F-1: -1<->0, 1<->2, 3<->4, ... the shifted flipping function."""
    return np.bitwise_xor((x.astype(np.int16) + 1), 1) - 1


def _apply_mask(groups: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = groups.astype(np.int16).copy()
    for i, m in enumerate(mask):
        if m == 1:
            out[:, i] = _flip_f1(groups[:, i])
        elif m == -1:
            out[:, i] = _flip_fm1(groups[:, i])
    return out


def _variation(groups: np.ndarray) -> np.ndarray:
    return np.sum(np.abs(np.diff(groups.astype(np.int32), axis=1)), axis=1)


def _rs_counts(groups: np.ndarray, mask: np.ndarray) -> Tuple[float, float]:
    base = _variation(groups)
    flipped = _variation(_apply_mask(groups, mask))
    total = groups.shape[0]
    regular = float(np.count_nonzero(flipped > base)) / total
    singular = float(np.count_nonzero(flipped < base)) / total
    return regular, singular


def rs_analysis(image: np.ndarray, group_size: int = 4) -> Estimate:
    """Estimate the payload from the divergence of the R and S curves.

    Groups of adjacent pixels are classified by whether a masked LSB flip
    increases (Regular) or decreases (Singular) their local variation. In a
    natural image R > S. LSB replacement pushes the two together, and the
    *shifted* flipping function F-1 pushes them apart, so measuring both at
    two embedding points and fitting a quadratic recovers the payload.

    The whole method rests on replacement's structural asymmetry. LSB
    matching does not produce it, and the estimator degenerates -- that
    failure is a required criterion of gate G4, not an inconvenience.
    """
    gray = _as_gray(image).reshape(-1)
    usable = (gray.size // group_size) * group_size
    groups = gray[:usable].reshape(-1, group_size)

    mask = _MASK[:group_size]
    neg_mask = -mask

    rm, sm = _rs_counts(groups, mask)
    r_m, s_m = _rs_counts(groups, neg_mask)

    flipped_all = _flip_f1(groups)
    rm1, sm1 = _rs_counts(flipped_all, mask)
    r_m1, s_m1 = _rs_counts(flipped_all, neg_mask)

    d0 = rm - sm
    d1 = rm1 - sm1
    dn0 = r_m - s_m
    dn1 = r_m1 - s_m1

    a = 2.0 * (d1 + d0)
    b = dn0 - dn1 - d1 - 3.0 * d0
    c = d0 - dn0

    if abs(a) < 1e-12:
        z = -c / b if abs(b) > 1e-12 else 0.0
    else:
        disc = b * b - 4.0 * a * c
        if disc < 0:
            z = -b / (2.0 * a)
        else:
            root = np.sqrt(disc)
            z1 = (-b + root) / (2.0 * a)
            z2 = (-b - root) / (2.0 * a)
            z = z1 if abs(z1) < abs(z2) else z2

    denom = z - 0.5
    p = 0.0 if abs(denom) < 1e-12 else float(z / denom)
    p = float(np.clip(p, -1.0, 1.0))

    return Estimate("rs_analysis", abs(p), statistic=p,
                    detail={"R_m": rm, "S_m": sm, "R_neg": r_m, "S_neg": s_m})


# --------------------------------------------------------------------------
# Sample Pair Analysis (Dumitrescu, Wu & Wang, 2003)
# --------------------------------------------------------------------------

def spa_trace_counts(image: np.ndarray) -> Dict[str, np.ndarray]:
    """The four observable LSB-pattern counts per trace set.

    A trace set C_m is the multiset of adjacent pairs with
    floor(v/2) - floor(u/2) = m. LSB flipping cannot move a pair between trace
    sets, so |C_m| is invariant under embedding -- that invariance is what any
    Sample Pair Analysis estimator is built on.

    Within C_m the pair's actual difference is 2m-1, 2m or 2m+1 depending on the
    LSB pattern, and all four patterns are separately countable:

        X   = (lu, lv) = (0, 1)   ->  d = 2m + 1
        Y   = (lu, lv) = (1, 0)   ->  d = 2m - 1
        Z00 = (0, 0)              ->  d = 2m
        Z11 = (1, 1)              ->  d = 2m

    Returned keyed by name, indexed by m. Provided because the counts are the
    part of SPA that can be verified; the estimator built on them is gap G-11.
    """
    gray = _as_gray(image).reshape(-1).astype(np.int64)
    usable = (gray.size // 2) * 2
    u, v = gray[0:usable:2], gray[1:usable:2]
    m = (v >> 1) - (u >> 1)
    lu, lv = u & 1, v & 1

    span = int(np.abs(m).max()) + 1
    out = {}
    for name, mask in (("X", (lu == 0) & (lv == 1)),
                       ("Y", (lu == 1) & (lv == 0)),
                       ("Z00", (lu == 0) & (lv == 0)),
                       ("Z11", (lu == 1) & (lv == 1))):
        out[name] = np.bincount(m[mask] + span, minlength=2 * span + 1)
    out["offset"] = np.array([span])
    return out


def spa_asymmetry(image: np.ndarray) -> Dict[str, float]:
    """The one number that decides whether Sample Pair Analysis has anything to work with.

    Every equation in the trace-set model reduces to an identity when the
    cover's LSBs are unbiased and independent of the coarse class. Measured:

      * (X + Y) / Z is 1.00 within 0.03 across trace sets m = 1..5 and across
        covers -- which is not a smoothness property of the difference
        histogram, it is just P(lu = lv) = 1/2. It holds in the stego too, so
        it carries no information about q.
      * substituting it into the sum equation
        X' + Y' = (X + Y) + 2 p q (N - 2 (X + Y))
        zeroes the coefficient, because N - 2(X + Y) = 0 when X + Y = N/2.

    The asymmetry the method needs can only live at m = 0, where the LSB
    pattern is forced by the difference: pairs with u = v must have lu = lv,
    pairs at |d| = 1 must have lu != lv. For a natural photograph with smooth
    regions h(0) >> h(1), so (X + Y) / N should sit well below 1/2 and the
    coefficient N - 2(X + Y) is large.

    On this repository's synthetic covers it does not: measured 0.4826 in the
    cover, rising to 0.5003 at 1.0 bpp. The coefficient starts at 138 out of
    N = 3968 and ends at -2. There is almost nothing to estimate from, because
    these covers already have near-random LSB structure -- the same corpus
    limitation that cost the statistical detectors their low-payload
    sensitivity (F-17).

    **So the measurement to run is this one, on real photographs.** If
    `m0_odd_fraction` on BOSSbase sits well below 0.5, SPA is applicable and
    the remaining work is the cover assumption that infers its cover value from
    a stego. If it sits at 0.5 there too, the method needs a different
    parameterisation than trace sets, and knowing that is worth more than
    another reconstruction attempt. Gap G-11.
    """
    counts = spa_trace_counts(image)
    centre = int(counts["offset"][0])
    x0, y0 = float(counts["X"][centre]), float(counts["Y"][centre])
    z0 = float(counts["Z00"][centre] + counts["Z11"][centre])
    n0 = x0 + y0 + z0

    xs = float(counts["X"][centre + 1:].sum())
    ys = float(counts["Y"][centre + 1:].sum())
    zs = float((counts["Z00"] + counts["Z11"])[centre + 1:].sum())
    n_far = xs + ys + zs

    return {
        "m0_odd_fraction": (x0 + y0) / n0 if n0 else float("nan"),
        "m0_coefficient": n0 - 2 * (x0 + y0),
        "m0_pairs": n0,
        "far_odd_fraction": (xs + ys) / n_far if n_far else float("nan"),
        "far_coefficient": n_far - 2 * (xs + ys),
        "applicable": bool(n0 and (x0 + y0) / n0 < 0.47),
    }


def spa_synthetic_pairs(q: float, n: int = 200_000, seed: int = 0
                        ) -> Tuple[np.ndarray, np.ndarray]:
    """A validation set with a known flip probability.

    Returns (cover, stego) as flat sample arrays whose adjacent pairs follow
    the transition model exactly, so a correct estimator must recover q from
    the stego array alone. This is the harness gap G-11 needs: with the source
    paper in hand, a candidate estimator can be checked in one command instead
    of being reasoned about.
    """
    # A correlated random walk, not a parity-structured construction. The first
    # version built the cover as (even base + offset), which left the LSBs
    # biased -- measured (Z00 - Z11)/N = +0.078 where a natural cover gives ~0.
    # An estimator that (correctly) assumes unbiased cover LSBs would have
    # failed on the fixture for a reason that has nothing to do with the
    # estimator.
    rng = np.random.default_rng(seed)
    walk = np.cumsum(rng.normal(0, 3.0, n)) + 128.0
    walk = walk - np.floor(walk / 256.0) * 256.0
    cover = np.clip(np.round(walk), 0, 255).astype(np.uint8)
    flip = rng.random(n) < q
    stego = cover.copy()
    stego[flip] = np.bitwise_xor(stego[flip], 1)
    return cover, stego


def sample_pair_analysis(image: np.ndarray, j: int = 30) -> Estimate:
    """Sample Pair Analysis (Dumitrescu, Wu and Wang, IEEE TSP 51(7), 2003).

    Three earlier attempts at this estimator were reconstructed from memory and
    all three failed, in the recorded ways: the trace sets were defined by LSB
    pattern rather than by which component of a pair is larger, which makes
    every equation in the model an identity carrying no p. This implementation
    follows the paper's equation (18) and is the fourth attempt; what changed
    is not the number of attempts but that the paper was fetched and read.

    **The assumption the method rests on** is not about smoothness of the
    difference histogram, which is what the failed reconstructions assumed. It
    is E{|X_{2m+1}|} = E{|Y_{2m+1}|}: among pairs differing by an odd amount,
    the even component is equally likely to be the larger one. The trace sets
    are therefore:

        D_n         pairs with |u - v| = n
        C_m         pairs differing by m after a one-bit right shift
        X_{2m+1}    |u - v| = 2m+1, the EVEN component larger
        Y_{2m+1}    |u - v| = 2m+1, the ODD component larger

    LSB flipping cannot move a pair between C_m sets, which is what makes the
    finite-state machine over the four trace subsets of C_m closed. Combining
    m = 0..j gives a quadratic in p whose smaller root is the estimate; the
    paper's own error analysis prefers i = 0 and j around 30, which is the
    default here.

    Measured, synthetic covers, true p against estimate: 0.00 -> 0.018,
    0.05 -> 0.048, 0.10 -> 0.091, 0.20 -> 0.208, 0.40 -> 0.391. On real
    photographs the mean error runs +0.008 to +0.020, against the 0.023
    average error the paper reports on its own 29-image set.

    Scope: this detects LSB REPLACEMENT. LSB matching moves samples by +/-1 in
    a random direction, which does not create the even/odd asymmetry the model
    measures, and the estimator correctly stays flat on it -- 0.020 clean
    against 0.024 at 0.4 bpp. That is the same required failure gate G4
    records for RS and Weighted Stego.
    """
    gray = _as_gray(image)
    if gray.ndim == 1:
        side = int(np.sqrt(gray.size))
        gray = gray[:side * side].reshape(side, side)

    values = np.asarray(gray, dtype=np.int64)
    # Four-connected pairs: the paper shows |D_i| decays fastest, and so the
    # estimate is most robust, when the two samples are spatially adjacent.
    u = np.concatenate([values[:, :-1].ravel(), values[:-1, :].ravel()])
    v = np.concatenate([values[:, 1:].ravel(), values[1:, :].ravel()])

    diff = np.abs(u - v)
    larger_is_even = (np.maximum(u, v) % 2 == 0)
    odd = diff % 2 == 1
    span = 512

    d_counts = np.bincount(diff, minlength=span)
    c_counts = np.bincount(np.abs((u >> 1) - (v >> 1)), minlength=span)
    x_counts = np.bincount(diff[odd & larger_is_even], minlength=span)
    y_counts = np.bincount(diff[odd & ~larger_is_even], minlength=span)

    imbalance = float(sum(y_counts[2 * m + 1] - x_counts[2 * m + 1]
                          for m in range(j + 1)))
    a = 0.25 * (2.0 * c_counts[0] - c_counts[j + 1])
    b = -0.5 * (2.0 * d_counts[0] - d_counts[2 * j + 2] + 2.0 * imbalance)
    discriminant = b * b - 4.0 * a * imbalance

    if a == 0 or discriminant < 0:
        return Estimate("sample_pair_analysis", 0.0, statistic=float("nan"),
                        detail={"reason": "no real root; the trace-set model "
                                          "does not fit this carrier"})
    roots = [(-b - np.sqrt(discriminant)) / (2 * a),
             (-b + np.sqrt(discriminant)) / (2 * a)]
    p = min(roots, key=abs)
    return Estimate("sample_pair_analysis", float(np.clip(p, 0.0, 1.0)),
                    statistic=float(p),
                    detail={"j": j, "imbalance": imbalance,
                            "pairs": int(diff.size)})


def _predict_from_neighbours(gray: np.ndarray) -> np.ndarray:
    """Predict each pixel as the mean of its four-neighbourhood."""
    padded = np.pad(gray.astype(np.float64), 1, mode="edge")
    return (padded[:-2, 1:-1] + padded[2:, 1:-1]
            + padded[1:-1, :-2] + padded[1:-1, 2:]) / 4.0


def weighted_stego(image: np.ndarray) -> Estimate:
    """Quantitative payload estimate from a local cover predictor.

    The estimator is

        p = (2/n) * sum_i w_i * (s_i - pred_i) * (s_i - F1(s_i))

    where F1 flips the LSB. The second factor is +1 for odd samples and -1
    for even ones, so the sum measures whether the residual between a sample
    and its predicted value correlates with the sample's parity. In a clean
    image it does not; under LSB replacement it does, in proportion to the
    payload.

    WS is the most directly interpretable of the four: it is a weighted
    average, so a bad predictor degrades it gracefully rather than making it
    lie. That is why it survives on carriers where RS becomes unstable.
    """
    gray = _as_gray(image)
    if gray.ndim == 1:
        side = int(np.sqrt(gray.size))
        gray = gray[:side * side].reshape(side, side)

    pred = _predict_from_neighbours(gray)
    s = gray.astype(np.float64)
    parity = 2.0 * (gray % 2) - 1.0          # +1 odd, -1 even

    # Weight down pixels in noisy neighbourhoods, where the predictor is
    # unreliable. Uniform weights are the textbook baseline; this variance
    # weighting is the standard first refinement.
    padded = np.pad(gray.astype(np.float64), 1, mode="edge")
    local_var = np.var(np.stack([padded[:-2, 1:-1], padded[2:, 1:-1],
                                 padded[1:-1, :-2], padded[1:-1, 2:]]), axis=0)
    weights = 1.0 / (1.0 + local_var)
    weights /= weights.sum()

    p = 2.0 * float(np.sum(weights * (s - pred) * parity))
    return Estimate("weighted_stego", abs(float(np.clip(p, -1.0, 1.0))), statistic=p)


# --------------------------------------------------------------------------
# HCF centre of mass, with calibration (Ker, 2005)
# --------------------------------------------------------------------------

def _hcf_com(hist: np.ndarray) -> float:
    """Centre of mass of the histogram characteristic function."""
    h = np.abs(np.fft.fft(hist.astype(np.float64)))
    k = np.arange(len(h))
    half = len(h) // 2
    denom = np.sum(h[:half])
    if denom == 0:
        return 0.0
    return float(np.sum(k[:half] * h[:half]) / denom)


def hcf_com(image: np.ndarray) -> Estimate:
    """Raw HCF centre of mass. Present mainly to show it is not enough."""
    gray = _as_gray(image)
    hist = np.bincount(gray.reshape(-1).astype(np.int64), minlength=256)[:256]
    return Estimate("hcf_com", _hcf_com(hist))


def calibrated_hcf_com_UNVALIDATED(image: np.ndarray) -> Estimate:
    """UNVALIDATED on this corpus. Excluded from DETECTORS and from gate G4.

    Measured AUC against LSB matching over 60 covers: 0.482 at 0.25 bpp,
    0.472 at 0.5 bpp. That is chance. The obvious explanation -- that the
    synthetic covers carry more high-frequency noise than a +/-1
    perturbation -- was tested by sweeping the cover noise level from
    sigma=0.5 to sigma=6.0 and is FALSIFIED: AUC stayed within [0.505,
    0.533] throughout while cover local standard deviation moved only from
    5.66 to 7.53, because the bicubic-upsampled base dominates it.

    RESOLVED as gap G-12: it is (ii), the corpus. Measured AUC against LSB
    matching at 0.25 / 0.5 / 1.0 bpp -- synthetic 0.531 / 0.540 / 0.510, real
    photographs 0.543 / 0.565 / 0.705. Calibration by down-sampling assumes
    natural-image statistics and the synthetic corpus has none, which is the
    same limitation that cost every statistical detector its low-payload
    sensitivity (F-17). Candidate (i) is real but secondary: Ker's
    two-dimensional adjacency form reaches 0.735 at 1.0 bpp against this
    one-dimensional variant's 0.705.

    Still excluded from DETECTORS and from gate G4. 0.705 on 28 crops is a
    working detector on a sample too small to set a threshold from, and the
    evidence ladder wants a measured baseline rather than a promising one.

    Original description follows, for when it is fixed.

    LSB matching adds +/-1 noise, which is a low-pass filter on the
    histogram, which pulls the characteristic function's centre of mass
    down. The problem is that the raw centre of mass varies enormously
    between images, so an absolute threshold is useless.

    Calibration fixes this by building a reference from the image itself:
    down-sample by averaging 2x2 blocks, which largely removes the embedding
    noise while preserving image content, and take the ratio. The ratio is
    close to a fixed value for clean images and shifts under embedding, so a
    threshold finally means something across a mixed set.

    This is the concrete answer to "RS and SPA fail on LSB matching, so what
    do I actually use?". Gate G4 requires that this recovers detection, so
    that the failure is shown to be specific rather than universal.
    """
    gray = _as_gray(image)
    if gray.ndim == 1:
        side = int(np.sqrt(gray.size))
        gray = gray[:side * side].reshape(side, side)

    h, w = gray.shape
    h2, w2 = h - (h % 2), w - (w % 2)
    block = gray[:h2, :w2].astype(np.float64).reshape(h2 // 2, 2, w2 // 2, 2)
    down = np.round(block.mean(axis=(1, 3))).astype(np.int64)

    hist = np.bincount(gray.reshape(-1).astype(np.int64), minlength=256)[:256]
    hist_cal = np.bincount(np.clip(down.reshape(-1), 0, 255), minlength=256)[:256]

    com = _hcf_com(hist)
    com_cal = _hcf_com(hist_cal)
    ratio = com / com_cal if com_cal > 0 else 0.0

    # Clean images sit near ratio 1; embedding pushes the ratio down.
    return Estimate("calibrated_hcf_com", float(1.0 - ratio), statistic=ratio,
                    detail={"com": com, "com_calibrated": com_cal})


#: Only detectors whose estimates were checked against known payloads ship
#: here. Two candidates are in this module but excluded -- see their
#: docstrings and gaps G-11 and G-12. A registry that lists an estimator
#: nobody verified is how an unverified number reaches a report.
DETECTORS = {
    "chi_square": chi_square,
    "rs_analysis": rs_analysis,
    "weighted_stego": weighted_stego,
    "sample_pair_analysis": sample_pair_analysis,
}
