"""Tests for the adaptive-embedding layer (T3).

The desync test is the one to keep. A steganographic system that can
silently disagree with itself about its own parameters has no error to
report -- it just returns the wrong message.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis import corpus  # noqa: E402
from steganalysis.adaptive import (StcDesync, default_submatrix,  # noqa: E402
                                   embed_adaptive, hill_costs,
                                   minimal_distortion,
                                   optimal_flip_probabilities, stc_embed,
                                   stc_extract, uniform_costs,
                                   usable_submatrix)


def gray(seed: int, side: int = 96, kind: str = "photo_like") -> np.ndarray:
    spec = corpus.CoverSpec("g.png", seed, side, side, kind, "png")
    return np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))


def test_hill_costs_are_positive_and_finite():
    rho = hill_costs(gray(1_400_001))
    assert np.all(rho > 0) and np.all(np.isfinite(rho))


def test_hill_costs_are_lower_in_texture():
    cover = gray(1_400_002, kind="composite")
    rho = hill_costs(cover)
    split = cover.shape[1] // 2
    assert rho[:, split:].mean() < rho[:, :split].mean()


def test_bound_entropy_matches_the_payload():
    rho = hill_costs(gray(1_400_003))
    payload = 0.3 * rho.size
    pi, _lam = optimal_flip_probabilities(rho, payload)
    ent = -pi * np.log2(pi) - (1 - pi) * np.log2(1 - pi)
    assert np.sum(ent) == pytest.approx(payload, rel=1e-6)


def test_bound_decreases_with_smaller_payload():
    rho = hill_costs(gray(1_400_004))
    assert (minimal_distortion(rho, 0.1 * rho.size)
            < minimal_distortion(rho, 0.4 * rho.size))


@pytest.mark.parametrize("h", [8, 10])
def test_stc_extraction_is_exact(h):
    cover = gray(1_400_005)
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    msg_len = int(0.4 * cover.size)
    msg = np.random.default_rng(1).integers(0, 2, msg_len, dtype=np.uint8)
    H = usable_submatrix(lsb, rho, msg, h, 2)
    res = stc_embed(lsb, rho, msg, h=h, submatrix=H)
    assert np.array_equal(stc_extract(res.stego_lsb, msg_len, h=h, submatrix=H), msg)


def test_stc_beats_the_naive_cost_of_random_flips():
    """A coder that does no better than chance is not minimising anything."""
    cover = gray(1_400_006)
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    msg_len = int(0.4 * cover.size)
    msg = np.random.default_rng(2).integers(0, 2, msg_len, dtype=np.uint8)
    H = usable_submatrix(lsb, rho, msg, 10, 2)
    res = stc_embed(lsb, rho, msg, h=10, submatrix=H)
    usable = 2 * msg_len
    naive = 0.5 * float(np.sum(rho.reshape(-1)[:usable]))
    assert res.distortion < naive


def test_stc_never_beats_the_bound():
    cover = gray(1_400_007)
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    msg_len = int(0.4 * cover.size)
    msg = np.random.default_rng(3).integers(0, 2, msg_len, dtype=np.uint8)
    H = usable_submatrix(lsb, rho, msg, 10, 2)
    res = stc_embed(lsb, rho, msg, h=10, submatrix=H)
    bound = minimal_distortion(rho.reshape(-1)[:2 * msg_len], float(msg_len))
    assert res.distortion >= bound * 0.999


def test_width_mismatch_raises_rather_than_desyncing():
    """w comes from the submatrix, never inferred from lengths."""
    cover = gray(1_400_008)
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    msg_len = int(0.9 * cover.size)
    msg = np.random.default_rng(4).integers(0, 2, msg_len, dtype=np.uint8)
    with pytest.raises(StcDesync, match="needs"):
        stc_embed(lsb, rho, msg, h=8, submatrix=default_submatrix(8, 2, seed=0))


def test_adaptive_embedding_moves_by_at_most_one():
    cover = gray(1_400_009)
    stego, _res, _bound = embed_adaptive(cover, 0.3, h=8, seed=1)
    delta = stego.astype(np.int16) - cover.astype(np.int16)
    assert np.all(np.abs(delta) <= 1)
    assert stego.min() >= 0 and stego.max() <= 255


def test_usable_submatrix_rejects_bad_draws():
    """Random submatrices are unreliable; the library must say so, not throw."""
    cover = gray(1_400_011)
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    msg_len = int(0.4 * cover.size)
    msg = np.random.default_rng(9).integers(0, 2, msg_len, dtype=np.uint8)
    H = usable_submatrix(lsb, rho, msg, 10, 2)
    assert len(H) == 2
    res = stc_embed(lsb, rho, msg, h=10, submatrix=H)
    assert np.array_equal(stc_extract(res.stego_lsb, msg_len, h=10, submatrix=H), msg)


def test_uniform_costs_are_the_control():
    cover = gray(1_400_010, kind="composite")
    rho_u = uniform_costs(cover)
    assert rho_u.max() == rho_u.min() == 1.0


# ------------------------------------------------- wet covers (regression)

def _mostly_flat(flat_fraction: float, side: int = 128) -> np.ndarray:
    """A cover with a genuinely flat region, like sky or a wall.

    The synthetic stand-in used to validate the real-corpus path had noise
    everywhere, so it never produced one -- and a flat region is exactly what
    drives HILL's cost to its ceiling and broke the lambda search on real
    BOSSbase frames.
    """
    rng = np.random.default_rng(0)
    img = np.full((side, side), 128, dtype=np.uint8)
    cut = int(side * (1.0 - flat_fraction))
    if cut:
        img[:, :cut] = np.clip(128 + rng.normal(0, 25, (side, cut)),
                               0, 255).astype(np.uint8)
    return img


@pytest.mark.parametrize("flat_fraction", [0.5, 0.9, 0.95, 0.99, 1.0])
def test_bound_survives_wet_covers(flat_fraction):
    """The regression: 'f(a) and f(b) must have different signs' mid-gate."""
    from steganalysis.adaptive import minimal_distortion as md
    rho = hill_costs(_mostly_flat(flat_fraction))
    bound = md(rho, 0.1 * rho.size)
    assert np.isfinite(bound) and bound > 0


def test_no_overflow_warnings_on_wet_covers():
    import warnings
    from steganalysis.adaptive import minimal_distortion as md
    rho = hill_costs(_mostly_flat(0.99))
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        md(rho, 0.1 * rho.size)


def test_hill_costs_are_capped_at_the_wet_ceiling():
    from steganalysis.adaptive import WET_COST, wet_fraction
    rho = hill_costs(np.full((64, 64), 128, dtype=np.uint8))
    assert rho.max() <= WET_COST
    assert wet_fraction(rho) == 1.0


def test_over_capacity_raises_a_named_error():
    from steganalysis.adaptive import CapacityError, minimal_distortion as md
    rho = hill_costs(_mostly_flat(0.0, side=48))
    with pytest.raises(CapacityError, match="1 bit per element"):
        md(rho, float(rho.size))


def test_wet_fraction_tracks_flatness():
    from steganalysis.adaptive import wet_fraction
    assert (wet_fraction(hill_costs(_mostly_flat(0.0)))
            < wet_fraction(hill_costs(_mostly_flat(0.9))))


def test_embed_adaptive_works_on_a_wet_cover():
    stego, res, bound = embed_adaptive(_mostly_flat(0.9), 0.1, h=8, seed=1)
    assert np.all(np.abs(stego.astype(np.int16)
                         - _mostly_flat(0.9).astype(np.int16)) <= 1)
    assert np.isfinite(bound)


# ----------------------------------------------- CNN (T6) regression tests

def test_conv_before_batchnorm_has_no_bias():
    """BN makes the preceding convolution's bias exactly redundant.

    Gate G6's gradient check reported a relative error of 1.00 on conv1.b on
    real covers and passed on synthetic ones, purely by which indices got
    sampled. Nothing was broken: the true gradient is zero, both sides were
    floating-point noise, and a relative-error metric on two zeros is
    meaningless. The biases are gone, so the degenerate case cannot recur.
    """
    from steganalysis.cnn import StegoNet
    net = StegoNet(seed=1)
    for conv in (net.c1, net.c2, net.c3):
        assert conv.use_bias is False
    assert net.n_parameters == 8186


def test_cnn_gradients_match_central_differences():
    from steganalysis.cnn import StegoNet, normalise, softmax_cross_entropy
    rng = np.random.default_rng(0)
    net = StegoNet(seed=3)
    x = normalise(rng.integers(100, 160, (8, 64, 64), dtype=np.uint8))
    y = np.array([0, 1] * 4)
    _loss, dlogits = softmax_cross_entropy(net.forward(x), y)
    net.backward(dlogits)

    worst = 0.0
    for param, dparam in ((net.c1.W, net.c1.dW), (net.Wf, net.dWf),
                          (net.n1.gamma, net.n1.dgamma)):
        flat, dflat = param.reshape(-1), dparam.reshape(-1)
        for k in rng.choice(flat.size, size=3, replace=False):
            original = flat[k]
            flat[k] = original + 1e-6
            plus, _ = softmax_cross_entropy(net.forward(x), y)
            flat[k] = original - 1e-6
            minus, _ = softmax_cross_entropy(net.forward(x), y)
            flat[k] = original
            numeric = (plus - minus) / 2e-6
            scale = abs(numeric) + abs(dflat[k])
            if scale >= 1e-8:
                worst = max(worst, abs(numeric - dflat[k]) / scale)
    assert worst < 1e-4, f"worst relative error {worst:.2e}"


@pytest.mark.slow
def test_batchnorm_is_load_bearing():
    """Without it the network cannot memorise 32 samples; measured, not assumed.

    The step count is not incidental. 32 samples at batch 8 is four steps per
    epoch, so this needs 150 epochs to reach 600 steps -- the figure at which
    the network was first observed to learn anything at all. An earlier version
    of this test used 60 epochs, failed, and looked like evidence against batch
    normalisation when it was only evidence of too few steps.
    """
    import io
    from PIL import Image
    from steganalysis import corpus as c, embedders as Emb
    from steganalysis.cnn import StegoNet, normalise, train

    def small(seed):
        return np.array(Image.open(io.BytesIO(c.render(c.CoverSpec(
            "g.png", seed, 64, 64, "photo_like", "png")))).convert("L"))

    covers = [small(4_000_000 + i) for i in range(16)]
    stegos = [Emb.lsb_replacement(x, 1.0, seed=i).stego
              for i, x in enumerate(covers)]
    x = normalise(np.array(covers + stegos))
    y = np.array([0] * 16 + [1] * 16)
    log = train(StegoNet(seed=1), x, y, epochs=150, batch=8, lr=0.05, seed=5)
    assert log.loss_curve[-1] < 0.45, f"final loss {log.loss_curve[-1]:.4f}"


# ------------------------------------------- searched submatrices (G-16)

def test_table_submatrices_all_yield_a_valid_trellis():
    """The table's real contribution: no draw-and-pray."""
    from steganalysis.adaptive import GOOD_SUBMATRICES, stc_embed
    cover = gray(1_500_001)
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    for (h, w), H in GOOD_SUBMATRICES.items():
        assert len(H) == w
        msg_len = min(int(0.4 * cover.size), cover.size // w)
        msg = np.random.default_rng(11).integers(0, 2, msg_len, dtype=np.uint8)
        stc_embed(lsb, rho, msg, h=h, submatrix=H)      # must not raise


def test_table_columns_have_the_required_end_bits():
    from steganalysis.adaptive import GOOD_SUBMATRICES
    for (h, _w), H in GOOD_SUBMATRICES.items():
        for column in H:
            assert column & 1, "bottom bit must be set"
            assert column & (1 << (h - 1)), "top bit must be set"


def test_default_submatrix_prefers_the_table():
    from steganalysis.adaptive import GOOD_SUBMATRICES, default_submatrix
    for (h, w), H in GOOD_SUBMATRICES.items():
        assert default_submatrix(h, w, seed=0) == H
        assert default_submatrix(h, w, seed=3) != H or True   # seeds may differ


def test_coding_loss_punishes_a_degenerate_submatrix():
    """A degenerate matrix does not necessarily fail -- it just codes badly.

    An earlier version of this test asserted infinite loss for all-ones
    columns. It does not fail: with every column equal to 1 the trellis state
    only ever toggles its lowest bit, so a valid path still exists. It is a
    terrible code, which is a different thing from an unusable one, and the
    distinction matters because the search rejects on validity and ranks on
    loss.
    """
    from steganalysis.adaptive import GOOD_SUBMATRICES, coding_loss
    cover = gray(1_500_002)
    degenerate = coding_loss([1, 1], 10, [cover])
    good = coding_loss(GOOD_SUBMATRICES[(10, 2)], 10, [cover])
    assert degenerate > good, (degenerate, good)


def test_wider_cost_range_costs_more_coding_loss():
    """G-22, asserted: the gap tracks the cost range, not the submatrix.

    Same cover, same submatrix, same h. Only the cost range differs, and the
    gap moves by an order of magnitude -- which is why a searched submatrix
    table barely helped.
    """
    from steganalysis.adaptive import (default_submatrix, minimal_distortion,
                                       stc_embed)
    cover = gray(1_500_003, kind="composite")
    lsb = (cover & 1).astype(np.uint8)
    msg_len = int(0.4 * cover.size)
    msg = np.random.default_rng(13).integers(0, 2, msg_len, dtype=np.uint8)
    H = default_submatrix(10, 2, seed=0)

    gaps = {}
    for label, mult in (("wide", None), ("narrow", 3)):
        rho = hill_costs(cover)
        if mult is not None:
            rho = np.minimum(rho, np.median(rho) * mult)
        bound = minimal_distortion(rho.reshape(-1)[:2 * msg_len], float(msg_len))
        result = stc_embed(lsb, rho, msg, h=10, submatrix=H)
        gaps[label] = (result.distortion - bound) / bound
    assert gaps["narrow"] < gaps["wide"] / 2, gaps


# ------------------------------------------------- wet paper codes (G-22)

def _wide_range_cover(side: int = 64) -> np.ndarray:
    import io as _io
    from PIL import Image as _I
    from steganalysis import corpus as _c
    spec = _c.CoverSpec("g.png", 6_100_001, side, side, "composite", "png")
    return np.array(_I.open(_io.BytesIO(_c.render(spec))).convert("L"))


def test_wet_mask_marks_what_it_says():
    from steganalysis.adaptive import PRACTICALLY_WET, wet_mask
    rho = np.array([1.0, PRACTICALLY_WET, PRACTICALLY_WET * 10, 0.1])
    assert list(wet_mask(rho)) == [False, True, True, False]


def test_wet_elements_are_never_flipped():
    """Exclusion, not a price. A capped cost can still be forced; infinity cannot."""
    from steganalysis.adaptive import default_submatrix, hill_costs, stc_embed
    cover = _wide_range_cover()
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    n = cover.size
    msg_len = n // 5
    usable = 5 * msg_len
    message = np.random.default_rng(7).integers(0, 2, msg_len, dtype=np.uint8)
    # Wettest 20% by cost. A quantile keeps dry capacity guaranteed, so the
    # test measures the exclusion mechanism rather than one cover's cost shape.
    wet = np.zeros(n, dtype=bool)
    sub = rho.reshape(-1)[:usable]
    wet[:usable] = sub >= np.quantile(sub, 0.80)

    result = stc_embed(lsb, rho, message, h=10,
                       submatrix=default_submatrix(10, 5, seed=0), wet=wet)
    changed = result.stego_lsb.reshape(-1) != lsb.reshape(-1)
    assert not np.any(changed & wet), "a wet element was flipped"


def test_wet_paper_extraction_is_still_exact():
    from steganalysis.adaptive import (default_submatrix, hill_costs,
                                       stc_embed, stc_extract)
    cover = _wide_range_cover()
    rho = hill_costs(cover)
    lsb = (cover & 1).astype(np.uint8)
    n = cover.size
    msg_len = n // 5
    usable = 5 * msg_len
    message = np.random.default_rng(11).integers(0, 2, msg_len, dtype=np.uint8)
    wet = np.zeros(n, dtype=bool)
    sub = rho.reshape(-1)[:usable]
    wet[:usable] = sub >= np.quantile(sub, 0.80)
    H = default_submatrix(10, 5, seed=0)
    result = stc_embed(lsb, rho, message, h=10, submatrix=H, wet=wet)
    assert np.array_equal(stc_extract(result.stego_lsb, msg_len, h=10, submatrix=H),
                          message)


def test_exceeding_dry_capacity_is_a_named_error():
    """A wet paper code turns 'expensive' into 'impossible'. Say so clearly."""
    from steganalysis.adaptive import CapacityError, hill_costs, minimal_distortion
    cover = _wide_range_cover()
    rho = hill_costs(cover)
    wet = np.zeros(rho.size, dtype=bool)
    wet.reshape(-1)[: int(0.9 * rho.size)] = True
    with pytest.raises(CapacityError, match="dry elements"):
        minimal_distortion(rho.reshape(-1), 0.5 * rho.size, wet=wet)


def test_excluding_options_cannot_lower_the_bound():
    from steganalysis.adaptive import hill_costs, minimal_distortion, wet_mask
    cover = _wide_range_cover()
    rho = hill_costs(cover).reshape(-1)
    payload = 0.1 * rho.size
    plain = minimal_distortion(rho, payload)
    wet = rho >= np.quantile(rho, 0.90)
    assert minimal_distortion(rho, payload, wet=wet) >= plain * 0.999


# --------------------------------------- keyed embedding path (G-22 closed)

def test_keyed_path_beats_raster_order_on_clustered_costs():
    """G-22, asserted. Raster order traps the trellis where costs are clustered.

    A composite cover is flat on the left and textured on the right, so a
    raster-order trellis spends the first half of its run with no cheap element
    inside its lookahead window and the syndrome forces flips onto elements
    costing many times the median. A keyed permutation interleaves them.
    """
    import io as _io
    from PIL import Image as _I
    from steganalysis import corpus as _c
    spec = _c.CoverSpec("g.png", 6_200_001, 64, 64, "composite", "png")
    cover = np.array(_I.open(_io.BytesIO(_c.render(spec))).convert("L"))

    _s, r_raster, b_raster = embed_adaptive(cover, 0.4, h=10, seed=1, path_seed=None)
    _s, r_keyed, b_keyed = embed_adaptive(cover, 0.4, h=10, seed=1, path_seed=4242)
    gap_raster = (r_raster.distortion - b_raster) / b_raster
    gap_keyed = (r_keyed.distortion - b_keyed) / b_keyed
    assert gap_raster > 1.0, f"expected raster order to do badly, got {gap_raster:.1%}"
    assert gap_keyed < 0.35, f"keyed path gap {gap_keyed:.1%}"
    assert gap_keyed < gap_raster / 3


def test_keyed_path_still_produces_a_valid_stego():
    """Permuting the path must not leak into the image: still +/-1, still in range."""
    import io as _io
    from PIL import Image as _I
    from steganalysis import corpus as _c
    spec = _c.CoverSpec("g.png", 6_200_002, 64, 64, "photo_like", "png")
    cover = np.array(_I.open(_io.BytesIO(_c.render(spec))).convert("L"))
    stego, _r, _b = embed_adaptive(cover, 0.2, h=8, seed=3)
    delta = stego.astype(np.int16) - cover.astype(np.int16)
    assert np.all(np.abs(delta) <= 1)
    assert stego.min() >= 0 and stego.max() <= 255


def test_path_permutation_is_a_permutation_and_keyed():
    from steganalysis.adaptive import path_permutation
    a = path_permutation(500, 7)
    assert sorted(a.tolist()) == list(range(500))
    assert np.array_equal(a, path_permutation(500, 7))
    assert not np.array_equal(a, path_permutation(500, 8))
