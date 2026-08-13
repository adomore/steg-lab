"""E-group tests: palette carriers.

The detector here only works after reconstructing an ordering that is not in
the pixel data. The first test asserts that directly -- raw indices carry
nothing -- because it is the whole point of the lab.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis import corpus  # noqa: E402
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402


def palette_cover(seed: int, side: int = 192) -> bytes:
    lab = load_lab("10_palette")
    return lab.to_palette_png(corpus.render(corpus.CoverSpec(
        "c.png", seed, side, side, ["texture", "photo_like"][seed % 2], "png")))


def payload(nbytes: int, seed: int) -> bytes:
    return np.random.default_rng(seed).integers(
        0, 256, nbytes, dtype=np.uint8).tobytes()


def test_luminance_order_is_derivable_from_the_file():
    """No key: the ordering is a function of the palette, which travels along."""
    lab = load_lab("10_palette")
    cover = palette_cover(9_600_001)
    indices, palette = lab._open_palette(cover)
    order = lab.luminance_order(palette)
    assert sorted(order.tolist()) == list(range(palette.shape[0]))
    luma = (0.299 * palette[:, 0] + 0.587 * palette[:, 1]
            + 0.114 * palette[:, 2])
    assert np.all(np.diff(luma[order]) >= -1e-9)


def test_payload_round_trips_byte_exact():
    lab = load_lab("10_palette")
    data = payload(800, 11)
    stego = lab.embed(palette_cover(9_600_002), data)
    assert lab.extract(stego, len(data)) == data


def test_embedding_only_moves_within_luminance_adjacent_pairs():
    """The reason EzStego is invisible: every swap is between neighbours."""
    lab = load_lab("10_palette")
    cover = palette_cover(9_600_003)
    stego = lab.embed(cover, payload(800, 12))
    ic, palette = lab._open_palette(cover)
    is_, _ = lab._open_palette(stego)
    order = lab.luminance_order(palette)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    moved = ic.reshape(-1) != is_.reshape(-1)
    assert moved.any()
    before = rank[ic.reshape(-1)[moved]]
    after = rank[is_.reshape(-1)[moved]]
    assert np.all(before // 2 == after // 2), "a swap crossed a pair boundary"


def test_raw_index_pairs_carry_nothing():
    """Without the sort there is no signal, which is the lab's whole claim."""
    lab = load_lab("10_palette")
    cover = palette_cover(9_600_004)
    stego = lab.embed(cover, payload(1500, 13))
    from scipy import stats as _st

    def raw_pair_p(blob):
        indices, palette = lab._open_palette(blob)
        hist = np.bincount(indices.reshape(-1),
                           minlength=palette.shape[0]).astype(float)
        obs, exp = [], []
        for k in range(0, (hist.size // 2) * 2, 2):
            a, b = hist[k], hist[k + 1]
            if a + b >= 8:
                obs.append(a)
                exp.append((a + b) / 2)
        chi2 = float(np.sum((np.array(obs) - np.array(exp)) ** 2 / np.array(exp)))
        return float(1.0 - _st.chi2.cdf(chi2, len(obs) - 1))

    assert raw_pair_p(stego) < 0.5, "raw index pairs should show nothing"


def test_detects_and_stays_quiet_on_clean():
    lab = load_lab("10_palette")
    covers = [palette_cover(9_610_000 + i) for i in range(12)]
    false_alarms = sum(1 for c in covers
                       if lab.detect(c, "c", baseline=None).verdict >= Evidence.E1)
    assert false_alarms == 0, f"{false_alarms}/12 false alarms"

    baseline = FalsePositiveBaseline("palette_sorted_pair_chi_square", 12, 0,
                                     0.60, "12 same-source clean palette PNGs")
    detected = sum(1 for i, c in enumerate(covers)
                   if lab.detect(lab.embed(c, payload(1200, 20 + i)), "s",
                                 baseline=baseline).verdict >= Evidence.E3)
    assert detected >= 10, f"detected {detected}/12"


def test_reaches_e4_because_no_key_is_needed():
    lab = load_lab("10_palette")
    data = payload(1200, 30)
    stego = lab.embed(palette_cover(9_620_001), data)
    baseline = FalsePositiveBaseline("palette_sorted_pair_chi_square", 12, 0,
                                     0.60, "clean palette PNGs")
    report = lab.detect(stego, "s", baseline=baseline, payload_bytes=len(data))
    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == data


def test_capacity_is_enforced():
    lab = load_lab("10_palette")
    with pytest.raises(ValueError, match="payload needs"):
        lab.embed(palette_cover(9_630_001), payload(100_000, 40))
