"""Adaptive embedding: cost functions, Syndrome-Trellis Codes, and the bound.

Everything before T3 embeds wherever the key says to. Adaptive embedding
asks a different question first: *where would a change be least noticeable?*
Assign every cover element a cost, then find the stego that satisfies the
message with minimum total cost.

Two pieces are needed and they are independent:

  * a **cost function** that says where changes are cheap. HILL is
    implemented here because it is three convolutions and genuinely
    competitive; WOW and S-UNIWARD are described in T3 and left to P3.
  * a **coding scheme** that gets close to the theoretical minimum for a
    given cost assignment. That is STC, and it is what makes adaptive
    embedding practical rather than aspirational.

The bound is what makes this checkable. For additive distortion and a
payload-limited sender, the optimal flipping probabilities follow a Gibbs
distribution, so the minimum achievable distortion can be computed exactly
and STC's output compared against it. Gate G3 does that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage
from scipy.optimize import brentq
from scipy.special import expit

# --------------------------------------------------------------------------
# Cost functions
# --------------------------------------------------------------------------

# The KB (Ker-Bohme) high-pass filter, used by HILL as its residual.
_KB = np.array([[-1, 2, -1],
                [2, -4, 2],
                [-1, 2, -1]], dtype=np.float64) / 4.0


#: Cost above which an element is effectively unusable -- "wet", in the wet
#: paper codes sense. HILL is 1/(filtered residual), and a genuinely flat
#: region of a real photograph -- sky, a wall, a blown highlight -- drives the
#: residual to zero and the cost to this ceiling. Naming it matters: on some
#: BOSSbase frames over 90% of elements land here, and a solver that does not
#: know that is solving a problem with almost no cheap capacity while assuming
#: it has plenty.
WET_COST = 1e10


def hill_costs(cover: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    """HILL cost function (Li, Wang, Huang, Li 2014).

    rho = 1 / (|I * K| * L1 * L2)

    A high-pass filter finds where the image is textured, then two averaging
    filters spread that judgement over a neighbourhood. The spreading is the
    part that matters: a single high-frequency pixel in a smooth region is a
    terrible place to embed even though the high-pass response there is
    large, and the low-pass stages suppress exactly that case.

    High cost means "do not touch". Smooth regions get large costs, textured
    regions small ones.
    """
    img = cover.astype(np.float64)
    residual = np.abs(ndimage.convolve(img, _KB, mode="mirror"))
    spread = ndimage.uniform_filter(residual, size=3, mode="mirror")
    spread = ndimage.uniform_filter(spread, size=15, mode="mirror")
    return np.minimum(1.0 / (spread + eps), WET_COST)


def uniform_costs(cover: np.ndarray) -> np.ndarray:
    """Every element equally expensive -- i.e. non-adaptive embedding.

    Included so gate G3 can hold the coding scheme fixed and vary only the
    cost assignment. Without this control, an improvement in detectability
    could be credited to STC when it belongs to HILL.
    """
    return np.ones_like(cover, dtype=np.float64)


# --------------------------------------------------------------------------
# The rate-distortion bound
# --------------------------------------------------------------------------

def _entropy(p: np.ndarray) -> np.ndarray:
    q = np.clip(p, 1e-12, 1 - 1e-12)
    return -q * np.log2(q) - (1 - q) * np.log2(1 - q)


class CapacityError(Exception):
    """The requested payload exceeds what this cover can carry."""


def optimal_flip_probabilities(rho: np.ndarray, payload_bits: float,
                               wet: Optional[np.ndarray] = None
                               ) -> Tuple[np.ndarray, float]:
    """Gibbs-optimal flipping probabilities for a payload-limited sender.

    pi_i = 1 / (1 + exp(lambda * rho_i))

    lambda is chosen so the total entropy equals the payload. The relation is
    monotone decreasing in lambda, so a bracketed root find is correct -- but
    only once the bracket actually contains the root, which is where the first
    version went wrong.

    It hardcoded the bracket as [1e-8, 1.0] and expanded only upward. With
    HILL costs reaching WET_COST = 1e10, lambda = 1e-8 already gives
    lambda * rho = 100 and pi = 0 for every wet element. On a BOSSbase frame
    where 92% of elements are wet, the entropy at the *lower* endpoint was
    already below the requested payload, so both endpoints had the same sign
    and scipy raised "f(a) and f(b) must have different signs" mid-gate.

    The bracket is now expanded in both directions, and pi is computed with
    expit rather than 1/(1+exp(x)) so large arguments saturate instead of
    overflowing -- the RuntimeWarnings were the visible half of this bug.
    """
    flat = rho.reshape(-1).astype(np.float64).copy()
    if wet is not None:
        # Infinite cost is what makes this a wet paper bound. Leaving wet
        # elements at their capped cost would compare the coder against a
        # bound that assumes they are usable, which is a bound for a different
        # problem and a flattering one.
        flat[np.asarray(wet).reshape(-1)] = np.inf
    n = flat.size
    n_dry = int(np.count_nonzero(np.isfinite(flat)))

    if payload_bits <= 0:
        return np.zeros_like(rho, dtype=np.float64), float("inf")
    if payload_bits >= n_dry:
        raise CapacityError(
            f"payload of {payload_bits:.0f} bits needs more than the "
            f"{n_dry} dry elements available (of {n}); binary embedding "
            f"carries at most 1 bit per element")

    def entropy_at(lam: float) -> float:
        return float(np.sum(_entropy(expit(-lam * flat))))

    # Lower endpoint: entropy must EXCEED the payload. Shrink until it does.
    lo = 1e-8
    for _ in range(60):
        if entropy_at(lo) > payload_bits:
            break
        lo /= 8.0
    else:
        raise CapacityError(
            f"could not bracket lambda from below for a payload of "
            f"{payload_bits:.0f} bits over {n} elements "
            f"(dry elements: {n_dry} of {n})")

    # Upper endpoint: entropy must fall BELOW the payload.
    hi = max(lo * 10.0, 1.0)
    for _ in range(80):
        if entropy_at(hi) < payload_bits:
            break
        hi *= 4.0
    else:
        raise CapacityError(
            f"could not bracket lambda from above for a payload of "
            f"{payload_bits:.0f} bits over {n} elements")

    lam = brentq(lambda l: entropy_at(l) - payload_bits, lo, hi, xtol=1e-14)
    return expit(-lam * flat).reshape(rho.shape), float(lam)


def minimal_distortion(rho: np.ndarray, payload_bits: float,
                       wet: Optional[np.ndarray] = None) -> float:
    """The distortion no coding scheme can beat at this payload."""
    pi, _ = optimal_flip_probabilities(rho, payload_bits, wet=wet)
    cost = np.asarray(rho, dtype=np.float64)
    if wet is not None:
        # pi is exactly 0 on wet elements, so their cost must not enter the
        # product as inf * 0.
        cost = np.where(np.asarray(wet), 0.0, cost)
    return float(np.sum(pi * cost))


#: An element this expensive is unusable in practice. WET_COST itself is the
#: wrong threshold to measure against: it is the exact clamp value, reached
#: only where the filtered residual is exactly zero. On BOSSbase almost
#: nothing hits it -- while the cost distribution still spans ten orders of
#: magnitude -- so a fraction measured at the ceiling reported 0.000 on the
#: very covers whose expensive elements broke the lambda search. One order of
#: magnitude below the ceiling is the practical line.
PRACTICALLY_WET = WET_COST / 10.0


def wet_mask(rho: np.ndarray, threshold: float = PRACTICALLY_WET) -> np.ndarray:
    """Boolean mask of elements too expensive to be worth changing.

    Capping a cost and excluding an element are different operations, and the
    difference is the whole of gap G-22. A capped cost is still finite, so the
    trellis will select that element whenever the syndrome leaves it no
    cheaper option -- and one forced expensive flip dominates the total. The
    costliest forced flip measured 2.12 against a median cost of 0.092.

    A wet paper code excludes instead: the element is simply not offered as a
    branch, so no syndrome can force it. What was a huge distortion becomes,
    in the worst case, an honest capacity failure.
    """
    return np.asarray(rho, dtype=np.float64) >= threshold


def wet_fraction(rho: np.ndarray) -> float:
    """Share of elements too expensive to be worth using.

    Worth reporting alongside any distortion figure: a cover that is 90% wet
    is being asked to carry its payload in the remaining 10%, and the bound
    reflects that even though nothing in the payload figure hints at it.
    """
    return float(np.mean(np.asarray(rho, dtype=np.float64) >= PRACTICALLY_WET))


def cost_profile(rho: np.ndarray) -> Dict[str, float]:
    """Quantiles of the cost distribution.

    A single ratio hides the shape. max/min on a BOSSbase cover is about
    2e10, which sounds like the cover is mostly unusable and is not: the bulk
    sits in a narrow band and a thin tail runs to the ceiling. The quantiles
    say which, and the difference decides whether adaptivity has room.
    """
    flat = np.asarray(rho, dtype=np.float64).reshape(-1)
    q = np.quantile(flat, [0.0, 0.5, 0.9, 0.99, 1.0])
    return {"min": float(q[0]), "median": float(q[1]),
            "p90": float(q[2]), "p99": float(q[3]), "max": float(q[4]),
            "wet_fraction": wet_fraction(flat),
            "p99_over_median": float(q[3] / q[1]) if q[1] > 0 else float("inf")}


# --------------------------------------------------------------------------
# Syndrome-Trellis Codes
# --------------------------------------------------------------------------

#: Submatrices found by searching candidates and keeping the one with the
#: lowest coding loss, produced by scripts/search-submatrices.py.
#:
#: Tabulating them is legitimate because the ranking *generalises*: the winner
#: chosen on two covers measured 9.1% on those and 9.0% on three held out, and
#: a mid-ranked candidate measured 10.1% and 10.3%. A submatrix is a property
#: of the code, not of the carrier, and the search confirms rather than assumes
#: that.
#:
#: What tabulating them does NOT do is close the gap to the bound. Among
#: candidates that produce a valid trellis at all, best and median differ by
#: about one percentage point; the gap itself is driven by the cost dynamic
#: range (see T3 section 3.8 and gap G-22). The table's real value is that
#: every entry is known to yield a valid path, which removes the 21-in-72
#: failure rate of drawing at random.
GOOD_SUBMATRICES: Dict[Tuple[int, int], List[int]] = {
    # Produced by scripts/search-submatrices.py --candidates 20 --validate.
    # "loss" is on the search covers, "held-out" on covers never scored against.
    (8, 2): [167, 211],     # loss 11.7%, held-out 12.6%, 11/20 draws valid
    (10, 2): [669, 625],    # loss  8.7%, held-out  9.3%, 15/20 draws valid
    (12, 2): [2915, 4047],  # loss  6.8%, held-out  7.1%, 14/20 draws valid
}


def default_submatrix(h: int, w: int = 2, seed: int = 0) -> List[int]:
    """A random parity-check submatrix, each column an h-bit integer.

    The top and bottom bits of every column are forced to 1. Filler, Judas
    and Fridrich note this is what keeps the trellis fully connected: a
    column with a zero top bit cannot influence the state that the next
    pruning step reads, and a column with a zero bottom bit wastes a row.
    """
    if seed == 0 and (h, w) in GOOD_SUBMATRICES:
        return list(GOOD_SUBMATRICES[(h, w)])
    rng = np.random.default_rng(seed)
    top = 1 << (h - 1)
    cols = []
    for _ in range(w):
        col = int(rng.integers(0, 1 << h)) | 1 | top
        cols.append(col)
    return cols


def coding_loss(submatrix: List[int], h: int, covers: List[np.ndarray],
                rate: float = 0.4, cost_fn=None) -> float:
    """Mean relative gap to the rate-distortion bound over a set of covers.

    Returns infinity when the trellis has no valid path for any cover, so a
    search can reject such candidates outright rather than discovering the
    problem later.
    """
    cost_fn = cost_fn or hill_costs
    w = len(submatrix)
    gaps = []
    for i, cover in enumerate(covers):
        rho = cost_fn(cover)
        lsb = (cover & 1).astype(np.uint8)
        n = cover.size
        msg_len = int(round(rate * n))
        if w * msg_len > n:
            msg_len = n // w
        usable = w * msg_len
        message = np.random.default_rng(900 + i).integers(
            0, 2, msg_len, dtype=np.uint8)
        bound = minimal_distortion(rho.reshape(-1)[:usable], float(msg_len))
        try:
            result = stc_embed(lsb, rho, message, h=h, submatrix=submatrix)
        except Exception:                                  # noqa: BLE001
            return float("inf")
        gaps.append((result.distortion - bound) / bound)
    return float(np.mean(gaps))


@dataclass
class StcResult:
    stego_lsb: np.ndarray        # the recovered x, one bit per cover element
    distortion: float
    payload_bits: int
    h: int
    changes: int

    @property
    def embedding_efficiency(self) -> float:
        return self.payload_bits / self.changes if self.changes else float("inf")


class StcDesync(Exception):
    """Raised when embedder and extractor would disagree about the matrix."""


def stc_embed(cover_lsb: np.ndarray, rho: np.ndarray, message: np.ndarray,
              h: int = 10, submatrix: Optional[List[int]] = None,
              wet: Optional[np.ndarray] = None) -> StcResult:
    """Viterbi search over the syndrome trellis.

    The trellis has 2^h states. Each cover element contributes one column of
    the parity-check matrix and two outgoing edges, for x_i = 0 and x_i = 1;
    taking the edge that disagrees with the cover costs rho_i. After every
    block of w elements the lowest state bit must equal the next message bit,
    so all mismatching states are pruned and the survivors shift down.

    Cost grows as O(2^h * n), which is why h is a knob rather than a
    constant: it trades run time directly against how close the result gets
    to the bound.
    """
    y = cover_lsb.reshape(-1).astype(np.uint8)
    cost = rho.reshape(-1).astype(np.float64).copy()
    if wet is not None:
        # Infinite cost on a branch is exclusion: the Viterbi search can never
        # take it, so no syndrome can force a wet element to flip. This is the
        # single line that turns a cost cap into a wet paper code.
        cost[np.asarray(wet).reshape(-1)] = np.inf
    m = message.reshape(-1).astype(np.uint8)

    n = y.size
    msg_len = m.size
    if msg_len == 0:
        return StcResult(y.copy().reshape(cover_lsb.shape), 0.0, 0, h, 0)

    # w comes from the submatrix, never from n // msg_len. Inferring it from
    # lengths lets the embedder and extractor reach different answers on the
    # same file -- the desync failure that silently destroys a stego system.
    # An explicit matrix is the shared secret; its width is part of it.
    H = list(submatrix) if submatrix is not None else default_submatrix(h, 2)
    w = len(H)
    if w < 1:
        raise StcDesync("submatrix must have at least one column")
    usable = w * msg_len
    if usable > n:
        raise StcDesync(f"payload needs {usable} elements at w={w}, "
                        f"cover has {n}")

    n_states = 1 << h
    INF = np.inf
    wght = np.full(n_states, INF)
    wght[0] = 0.0
    path = np.zeros((usable, n_states), dtype=np.uint8)

    states = np.arange(n_states)
    idx = 0
    for i in range(msg_len):
        for j in range(w):
            col = H[j]
            c = cost[idx]
            # x_i = 0 keeps the state; x_i = 1 xors in this column.
            w0 = wght + (c if y[idx] == 1 else 0.0)
            w1 = wght[states ^ col] + (c if y[idx] == 0 else 0.0)
            take_one = w1 < w0
            path[idx] = take_one.astype(np.uint8)
            wght = np.where(take_one, w1, w0)
            idx += 1

        # Prune: the low bit of the state must equal this message bit.
        keep = wght[m[i]::2]
        wght = np.full(n_states, INF)
        wght[: n_states >> 1] = keep

    distortion = float(wght[0])
    if not np.isfinite(distortion):
        if wet is not None:
            dry = int(np.count_nonzero(~np.asarray(wet).reshape(-1)[:usable]))
            raise CapacityError(
                f"no valid path with wet elements excluded: {msg_len} bits over "
                f"{dry} dry elements of {usable} covered. This is a capacity "
                f"failure, not a coding failure -- lower the payload or accept "
                f"that this carrier cannot hold it")
        raise RuntimeError("trellis has no valid path; increase h or the submatrix rank")

    # Backward pass: undo the shifts and read off the chosen edges.
    x = np.empty(usable, dtype=np.uint8)
    state = 0
    idx = usable - 1
    for i in range(msg_len - 1, -1, -1):
        state = (state << 1) | int(m[i])
        for j in range(w - 1, -1, -1):
            bit = path[idx, state]
            x[idx] = bit
            if bit:
                state ^= H[j]
            idx -= 1

    out = y.copy()
    out[:usable] = x
    changes = int(np.count_nonzero(out != y))
    return StcResult(out.reshape(cover_lsb.shape), distortion, msg_len, h, changes)


def stc_extract(stego_lsb: np.ndarray, msg_len: int, h: int = 10,
                submatrix: Optional[List[int]] = None) -> np.ndarray:
    """Compute the syndrome. Extraction is a single forward pass, no search.

    `submatrix` is required in practice: its width w is what tells the
    extractor how many elements each message bit spans, and guessing it from
    n // msg_len desynchronises whenever w * msg_len != n.
    """
    x = stego_lsb.reshape(-1).astype(np.uint8)
    n = x.size
    H = list(submatrix) if submatrix is not None else default_submatrix(h, 2)
    w = len(H)
    if w * msg_len > n:
        raise StcDesync(f"cannot read {msg_len} bits at w={w} from {n} elements")

    out = np.empty(msg_len, dtype=np.uint8)
    state = 0
    idx = 0
    for i in range(msg_len):
        for j in range(w):
            if x[idx]:
                state ^= H[j]
            idx += 1
        out[i] = state & 1
        state >>= 1
    return out


# --------------------------------------------------------------------------
# End-to-end adaptive embedding
# --------------------------------------------------------------------------

def path_permutation(n: int, seed: int) -> np.ndarray:
    """The keyed order in which the trellis visits cover elements.

    This is the resolution of gap G-22, and it is embarrassingly simple.

    The trellis has a lookahead of h and it visits elements in whatever order
    it is handed. Handed them in raster order, it walks through the image
    spatially -- and costs are spatially clustered, because texture is. On a
    cover whose left half is flat and right half textured, the trellis spends
    the first half of its run with no cheap element anywhere inside its window,
    so the syndrome forces flips onto elements costing 24x the median. Those
    few forced flips then dominate the distortion.

    A keyed permutation interleaves cheap and expensive elements, so a cheap
    option is almost always within reach of the window. Measured, at h=10:

        cover        w    raster    permuted
        photo_like   2     11.6%       7.2%
        photo_like  20     38.7%      22.8%
        composite    2    283.7%      22.0%
        composite   10     71.3%      15.2%
        composite   20    146.1%      18.6%

    Every configuration lands in a 7-27% band instead of spanning 12% to 284%,
    and the costliest forced flip on the composite cover at w=10 falls from
    1.59 to 0.083 -- from 19x the median to the median itself.

    The permutation is part of the shared secret, like the submatrix. Every
    real implementation keys the embedding path; this one did not, and the four
    sub-hypotheses that G-22 burned through were all consequences of that:
    submatrix quality could not fix an ordering problem, cost dynamic range was
    a proxy for spatial clustering, and wet paper codes removed the clustered
    capacity instead of reordering access to it.
    """
    return np.random.default_rng(seed).permutation(n)


def embed_adaptive(cover: np.ndarray, rate: float, h: int = 10,
                   cost_fn=hill_costs, seed: int = 0,
                   w: Optional[int] = None,
                   wet_paper: bool = False,
                   path_seed: Optional[int] = 4242
                   ) -> Tuple[np.ndarray, StcResult, float]:
    """Embed at a relative payload using STC over the given cost function.

    `w` defaults to n // msg_len, which is how STC is meant to be used: the
    trellis then spans the whole cover and every element is a candidate.

    `wet_paper` is opt-in, not on by default, and the reason is measured. A wet
    paper code turns "expensive" into "impossible", and on this implementation
    that trade never paid: where exclusion was feasible it changed the gap to
    the bound by 0% (and once by -9%), and where it would have mattered it made
    the payload infeasible instead of cheap. Defaulting it on only converted
    working embeddings into capacity failures. See gap G-22.

    Fixing w at 2 -- as this function originally did -- silently changes the
    experiment. At 0.05 bpp it makes the covered region 2 * 0.05n = 10% of the
    image, taken as a raster *prefix*, so embedding only ever touched the top
    tenth. The measured change density in textured versus smooth regions then
    said more about what happened to be in the top tenth than about the cost
    function: with UNIFORM costs, where placement should be content-blind, the
    ratio came out at 0.55. A control that fails is how you find out the
    experiment is confounded.

    Returns (stego image, STC result, minimal achievable distortion).
    """
    rho = cost_fn(cover)
    n = cover.size
    msg_len = max(int(round(rate * n)), 1)
    if w is None:
        w = max(n // msg_len, 1)
    msg_len = max(min(msg_len, n // w), 1)

    rng = np.random.default_rng(seed)
    message = rng.integers(0, 2, msg_len, dtype=np.uint8)

    cover_lsb = (cover & 1).astype(np.uint8)
    wet_full = wet_mask(rho) if wet_paper else None

    # Keyed embedding path. path_seed=None reverts to raster order, which is
    # only useful for reproducing the G-22 measurements.
    if path_seed is None:
        order = np.arange(n)
    else:
        order = path_permutation(n, path_seed)

    rho_p = rho.reshape(-1)[order]
    lsb_p = cover_lsb.reshape(-1)[order]
    wet_p = None if wet_full is None else wet_full.reshape(-1)[order]

    result = stc_embed(lsb_p, rho_p, message, h=h,
                       submatrix=default_submatrix(h, w, seed=1), wet=wet_p)

    flip_p = (result.stego_lsb.reshape(-1) != lsb_p)
    flip = np.zeros(n, dtype=bool)
    flip[order] = flip_p
    flip = flip.reshape(cover.shape)
    stego = cover.astype(np.int16).copy()
    # Move by +/-1 in the direction that stays in range, like LSB matching.
    step = np.where(rng.random(cover.shape) < 0.5, -1, 1).astype(np.int16)
    step[cover == 0] = 1
    step[cover == 255] = -1
    stego[flip] += step[flip]

    # The bound must be computed over the elements STC actually covers, not
    # over the whole image. With w=2 the trellis spans 2*msg_len elements; a
    # bound taken over all n solves an easier problem (same payload, more
    # room) and would flatter the coder by tens of percent.
    # The bound must be scoped to the same elements the trellis covered --
    # which, with a keyed path, are the first `usable` in PERMUTED order.
    usable = w * msg_len
    bound = minimal_distortion(
        rho_p[:usable], float(msg_len),
        wet=None if wet_p is None else wet_p[:usable])
    return stego.astype(np.uint8), result, bound


def usable_submatrix(cover_lsb: np.ndarray, rho: np.ndarray,
                     message: np.ndarray, h: int, w: int = 2,
                     max_tries: int = 16) -> List[int]:
    """Find a submatrix whose trellis actually has a valid path.

    Random submatrices are not reliably usable: at h=10, w=2 roughly a
    quarter of them leave the terminal state unreachable, and the embedder
    then has nothing to return. Published STC uses *designed* submatrices;
    until those land (gap G-16) callers need a way to reject bad draws rather
    than discovering the problem as an exception three layers up.

    The probe uses the ACTUAL message, not a placeholder. Feasibility is a
    property of the (matrix, message) pair -- pruning selects states by
    message bit -- so a matrix that embeds all-zeros can still fail on the
    payload you meant to send. An earlier version probed with zeros and
    passed matrices that then threw at the real call.
    """
    for seed in range(max_tries):
        H = default_submatrix(h, w, seed=seed)
        try:
            stc_embed(cover_lsb, rho, message, h=h, submatrix=H)
            return H
        except RuntimeError:
            continue
    raise StcDesync(f"no usable submatrix found for h={h}, w={w} in "
                    f"{max_tries} tries; increase h")
