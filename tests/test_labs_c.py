"""C-group tests: feature sets, the ensemble classifier, and lab 09.

The test that matters here is `test_lab09_refuses_to_run_untrained`. An API
that quietly returns a number when it has no basis for one is how an
unfounded verdict reaches a report, and this lab's whole point is that a
feature-set classifier has no source-independent decision rule.
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

from labs.common import load_lab  # noqa: E402
from steganalysis import corpus, detectors as D, embedders as E  # noqa: E402
from steganalysis.evidence import Evidence  # noqa: E402
from steganalysis.features import (FEATURE_DIM, FldEnsemble,  # noqa: E402
                                   min_error_probability, spam686)

MATCHED = ["texture", "photo_like"]


def gray(seed: int, kinds=MATCHED, side: int = 192) -> np.ndarray:
    spec = corpus.CoverSpec("g.png", seed, side, side,
                            kinds[seed % len(kinds)], "png")
    return np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))


def gray_png(seed: int, kinds=MATCHED, side: int = 192) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(gray(seed, kinds, side), mode="L").save(
        buf, format="PNG", compress_level=6, optimize=False)
    return buf.getvalue()


# ---------------------------------------------------------------- features

def test_spam_dimensionality():
    f = spam686(gray(900_001))
    assert f.shape == (FEATURE_DIM,) == (686,)
    assert np.all(np.isfinite(f))


def test_spam_is_conditionally_normalised():
    """Each (u, v) conditioning state sums to 1, or to 0 when never observed."""
    f = spam686(gray(900_002))
    for half in (f[:343], f[343:]):
        rows = half.reshape(49, 7).sum(axis=1)
        assert np.all((np.isclose(rows, 1.0)) | (np.isclose(rows, 0.0)))


def test_spam_responds_to_both_embedders():
    """The claim that makes T5 work: SPAM models the cover, not the artefact."""
    cover = gray(900_003)
    f_cover = spam686(cover)
    d_match = np.linalg.norm(spam686(E.lsb_matching(cover, 1.0, seed=1).stego) - f_cover)
    d_repl = np.linalg.norm(spam686(E.lsb_replacement(cover, 1.0, seed=1).stego) - f_cover)
    assert d_match > 0 and d_repl > 0
    # Neither embedder should be invisible to it.
    assert min(d_match, d_repl) > 0.25 * max(d_match, d_repl)


# ---------------------------------------------------------------- ensemble

@pytest.fixture(scope="module")
def trained():
    covers = [gray(910_000 + i) for i in range(60)]
    fc = np.array([spam686(c) for c in covers])
    fs = np.array([spam686(E.lsb_matching(c, 1.0, seed=i).stego)
                   for i, c in enumerate(covers)])
    clf = FldEnsemble(n_learners=25, d_sub=150, seed=3).fit(fc[:40], fs[:40])
    return clf, fc[40:], fs[40:]


def test_ensemble_separates_better_than_chance(trained):
    clf, fc_te, fs_te = trained
    pe, _ = min_error_probability(clf.decision_function(fc_te),
                                  clf.decision_function(fs_te))
    assert pe < 0.40, f"P_E={pe:.3f}"


def test_ensemble_beats_structural_detectors_on_matching(trained):
    """The gap lab 08 documented, closed and asserted."""
    clf, fc_te, fs_te = trained
    pe_ens, _ = min_error_probability(clf.decision_function(fc_te),
                                      clf.decision_function(fs_te))
    covers = [gray(910_000 + 40 + i) for i in range(20)]
    c = np.array([float(D.rs_analysis(x)) for x in covers])
    s = np.array([float(D.rs_analysis(E.lsb_matching(x, 1.0, seed=i).stego))
                  for i, x in enumerate(covers)])
    pe_rs, _ = min_error_probability(c, s)
    assert pe_ens < pe_rs - 0.10, f"ensemble={pe_ens:.3f} rs={pe_rs:.3f}"


def test_decision_function_is_a_vote_fraction(trained):
    clf, fc_te, _ = trained
    scores = clf.decision_function(fc_te)
    assert np.all((scores >= 0.0) & (scores <= 1.0))


def test_min_error_probability_is_symmetric_at_chance():
    rng = np.random.default_rng(0)
    a = rng.normal(size=200)
    b = rng.normal(size=200)
    pe, _ = min_error_probability(a, b)
    assert 0.35 < pe <= 0.5


# ------------------------------------------------------------------- lab 09

def test_lab09_refuses_to_run_untrained():
    """No classifier, no verdict. The API tells the truth about what it needs."""
    lab = load_lab("09_feature_based")
    stego = lab.embed(gray_png(920_001), rate=1.0)
    assert lab.detect(stego, "stego.png", baseline=None).verdict == Evidence.E0


def test_lab09_detects_matching_once_trained():
    """Asserted as a RATE, not per image.

    The first version of this test embedded one payload and asserted the
    classifier caught it. That test was wrong in a way worth keeping a note
    about: a classifier with P_E near 0.3 misses individual images by
    construction, so a single-image assertion tests luck. Everything from
    lab 07 onward is a statistical verdict, and statistical verdicts have to
    be asserted statistically.
    """
    lab = load_lab("09_feature_based")
    covers = [gray_png(921_000 + i) for i in range(40)]
    clf = lab.train(covers, rate=1.0, matching=True)
    cal = lab.calibrate(clf, [gray_png(922_000 + i) for i in range(20)], rate=1.0)

    from steganalysis.evidence import FalsePositiveBaseline
    baseline = FalsePositiveBaseline("spam686_fld_ensemble", cal["n_clean"],
                                     cal["false_positives"], cal["threshold"],
                                     "20 held-out same-source covers")

    detected = 0
    for i in range(16):
        stego = lab.embed(gray_png(923_000 + i), rate=1.0, seed=i)
        report = lab.detect(stego, f"stego{i}.png", baseline=baseline,
                            classifier=clf, threshold=cal["threshold"])
        if report.verdict >= Evidence.E3:
            detected += 1
            assert all(f.payload is None for f in report.findings)

    false_alarms = 0
    for i in range(16):
        clean = gray_png(926_000 + i)
        if lab.detect(clean, f"clean{i}.png", baseline=baseline,
                      classifier=clf, threshold=cal["threshold"]).verdict >= Evidence.E3:
            false_alarms += 1

    assert detected > false_alarms, (
        f"detected {detected}/16 stego, {false_alarms}/16 false alarms")
    assert detected >= 9, f"detection rate {detected}/16 is not above chance"


def test_lab09_caps_at_e3():
    """A classifier confirms existence. It never produces a payload."""
    lab = load_lab("09_feature_based")
    covers = [gray_png(924_000 + i) for i in range(30)]
    clf = lab.train(covers)
    from steganalysis.evidence import FalsePositiveBaseline
    baseline = FalsePositiveBaseline("spam686_fld_ensemble", 30, 0, 0.5, "same source")
    report = lab.detect(lab.embed(gray_png(925_001)), "s.png",
                        baseline=baseline, classifier=clf, threshold=0.5)
    assert report.verdict <= Evidence.E3
