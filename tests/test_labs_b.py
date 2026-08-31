"""B-group lab tests: the statistical layer.

The important test in this file is `test_lab08_matching_defeats_structural_
detectors`. It asserts a *failure* -- that the shipped detectors cannot
separate LSB matching from clean covers. Most test suites only encode what
should work, which leaves the reader with no way to tell a limitation from
an oversight. This one pins the limitation down with a number.
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

from labs.common import load_lab, measure_baseline  # noqa: E402
from steganalysis import corpus, detectors as D, embedders as E  # noqa: E402
from steganalysis.evidence import Evidence  # noqa: E402

N_CLEAN = 40


def gray_cover(seed: int, side: int = 256) -> np.ndarray:
    spec = corpus.CoverSpec("g.png", seed, side, side,
                            ["texture", "photo_like"][seed % 2], "png")
    return np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))


def gray_png(seed: int, side: int = 256) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(gray_cover(seed, side), mode="L").save(
        buf, format="PNG", compress_level=6, optimize=False)
    return buf.getvalue()


# --------------------------------------------------------------- embedders

def test_lsb_replacement_round_trip():
    cover = gray_cover(600_001)
    res = E.lsb_replacement(cover, 0.25, seed=1)
    assert res.bits_embedded == int(round(0.25 * cover.size))
    # About half the written bits already matched, so about half caused a change.
    assert 0.4 < res.changes / res.bits_embedded < 0.6
    assert res.embedding_efficiency == pytest.approx(2.0, abs=0.15)


def test_lsb_matching_never_moves_more_than_one():
    cover = gray_cover(600_002)
    res = E.lsb_matching(cover, 0.5, seed=2)
    delta = res.stego.astype(np.int16) - cover.astype(np.int16)
    assert np.all(np.abs(delta) <= 1)
    assert res.stego.min() >= 0 and res.stego.max() <= 255


def test_lsb_matching_preserves_pair_structure():
    """The one-line difference that costs the structural detectors everything.

    Replacement can only ever move within a value pair, so floor(x/2) is
    invariant. Matching crosses pair boundaries, and that is precisely why
    RS and WS lose their footing.
    """
    cover = gray_cover(600_003)
    rep = E.lsb_replacement(cover, 1.0, seed=3).stego
    mat = E.lsb_matching(cover, 1.0, seed=3).stego
    assert np.array_equal(rep >> 1, cover >> 1)
    assert not np.array_equal(mat >> 1, cover >> 1)


def test_f5_matrix_encoding_efficiency():
    coeffs = np.random.default_rng(7).integers(-12, 13, (400, 64))
    for k in (1, 2, 3, 4):
        res = E.f5(coeffs, rate=0.3, k=k, seed=k, no_shrinkage=True)
        assert res.embedding_efficiency == pytest.approx(
            res.theoretical_efficiency, rel=0.05)


def test_f5_shrinkage_costs_payload():
    coeffs = np.random.default_rng(8).integers(-6, 7, (600, 64))
    plain = E.f5(coeffs, rate=1.0, k=3, seed=1)
    ns = E.f5(coeffs, rate=1.0, k=3, seed=1, no_shrinkage=True)
    assert plain.shrinkage_events > 0
    assert ns.shrinkage_events == 0
    assert plain.bits_embedded < ns.bits_embedded


def test_jsteg_never_touches_zero_or_one():
    coeffs = np.random.default_rng(9).integers(-8, 9, (300, 64))
    stego = E.jsteg(coeffs, rate=1.0, seed=1).stego
    protected = (coeffs == 0) | (coeffs == 1)
    assert np.array_equal(stego[protected], coeffs[protected])


# ---------------------------------------------------------------- detectors

@pytest.mark.parametrize("name", ["rs_analysis", "weighted_stego"])
def test_detector_estimates_track_payload(name):
    fn = D.DETECTORS[name]
    cover = gray_cover(600_010)
    low = float(fn(E.lsb_replacement(cover, 0.10, seed=1).stego))
    high = float(fn(E.lsb_replacement(cover, 0.75, seed=1).stego))
    assert high > low
    assert float(fn(cover)) < high


def test_unvalidated_detectors_are_not_in_the_registry():
    """Only validated detectors are reachable by name.

    Sample Pair Analysis moved INTO the registry once it was implemented from
    the source paper rather than from memory (gap G-11), and its accuracy is
    asserted in tests/test_core.py. The calibrated HCF-COM has not: it reaches
    AUC 0.705 on real photographs and 0.510 on synthetic ones, and a detector
    whose usefulness depends on a corpus the repository cannot ship is not one
    a caller should reach by name. Gap G-12.
    """
    assert "calibrated_hcf_com" not in D.DETECTORS
    assert hasattr(D, "calibrated_hcf_com_UNVALIDATED")
    assert "sample_pair_analysis" in D.DETECTORS, "G-11 closed; SPA is validated"


# ------------------------------------------------------------------- lab 07

def test_lab07_detects_lsb_replacement():
    lab = load_lab("07_lsb_replacement")
    stego = lab.embed(gray_png(600_020), rate=0.75)
    baseline = measure_baseline(lab.detect, "weighted_stego", N_CLEAN, "png", 610_000)
    report = lab.detect(stego, "stego.png", baseline=baseline)
    assert report.verdict == Evidence.E3
    assert any(f.detector == "weighted_stego" for f in report.findings)


def test_lab07_caps_at_e3_not_e4():
    """Statistical confirmation is not payload recovery, and must not claim to be."""
    lab = load_lab("07_lsb_replacement")
    stego = lab.embed(gray_png(600_021), rate=1.0)
    baseline = measure_baseline(lab.detect, "rs_analysis", N_CLEAN, "png", 611_000)
    report = lab.detect(stego, "stego.png", baseline=baseline)
    assert report.verdict == Evidence.E3
    assert all(f.payload is None for f in report.findings)


def test_lab07_sequential_embedding_is_extractable():
    lab = load_lab("07_lsb_replacement")
    payload = b"lab07 sequential payload, recoverable without a key"
    stego = lab.embed(gray_png(600_022), payload=payload, sequential=True)
    assert lab.extract_sequential(stego, len(payload)) == payload


MATCHED = ["texture", "photo_like"]


@pytest.mark.parametrize("detector,seed", [("rs_analysis", 612_000),
                                           ("weighted_stego", 613_000)])
def test_lab07_zero_false_positives_on_matched_source(detector, seed):
    lab = load_lab("07_lsb_replacement")
    baseline = measure_baseline(lab.detect, detector, N_CLEAN, "png", seed,
                                kinds=MATCHED)
    assert baseline.n_false_positives == 0, baseline.describe()


@pytest.mark.parametrize("detector", ["rs_analysis", "weighted_stego"])
def test_cover_source_mismatch_inflates_false_positives(detector):
    """Cover-source mismatch, measured on the way past.

    The same detector at the same threshold, differing only in which covers
    the baseline was drawn from. Adding flat and gradient images -- where
    local variation is nearly zero and both estimators become unstable --
    drives the false-positive rate from nothing to something that would ruin
    a case.

    This is the failure T4 and T5 describe in the abstract. It was found here
    by accident, which is the usual way, and it is the concrete reason the
    evidence ladder insists a baseline come from the SAME source rather than
    from a source that seems similar.
    """
    lab = load_lab("07_lsb_replacement")
    matched = measure_baseline(lab.detect, detector, N_CLEAN, "png", 614_000,
                               kinds=MATCHED)
    mixed = measure_baseline(lab.detect, detector, N_CLEAN, "png", 614_000)
    assert matched.fpr == 0.0, matched.describe()
    assert mixed.fpr > 0.10, (
        f"expected mismatch to inflate the FPR; matched={matched.describe()} "
        f"mixed={mixed.describe()}")


# ------------------------------------------------------------------- lab 08

def test_lab08_matching_defeats_structural_detectors():
    """The required failure, asserted as a measured quantity.

    If a future change makes a structural detector work on LSB matching,
    this test goes red and demands an explanation -- which is correct, since
    the most likely cause is a broken embedder, not a breakthrough.
    """
    lab = load_lab("08_lsb_matching")
    covers = [gray_png(620_000 + i) for i in range(30)]
    for detector in ("rs_analysis", "weighted_stego"):
        result = lab.separation(covers, rate=0.5, detector=detector)
        assert result["deviation_from_chance"] < 0.15, result


def test_lab08_reports_nothing_rather_than_guessing():
    lab = load_lab("08_lsb_matching")
    stego = lab.embed(gray_png(620_100), rate=1.0)
    assert lab.detect(stego, "stego.png", baseline=None).verdict == Evidence.E0
    assert lab.detect(gray_png(620_101), "clean.png", baseline=None).verdict == Evidence.E0


def test_lab08_stego_is_a_valid_image():
    lab = load_lab("08_lsb_matching")
    stego = lab.embed(gray_png(620_200), rate=0.5)
    arr = np.array(Image.open(io.BytesIO(stego)))
    assert arr.shape == (256, 256)


# ------------------------------------- pipeline coverage of every carrier

def test_every_lab_is_either_routed_or_a_stated_exception():
    """No lab falls out of the pipeline silently.

    `08_lsb_matching` and `09_feature_based` are absent on purpose -- one has
    no working detector, the other needs a trained classifier a blind pipeline
    cannot supply -- and `pipeline.UNROUTED_BY_DESIGN` says so. Everything else
    must be reachable. The failure this prevents is the one gap G7 already hit
    once: a lab that exists, has tests, and is never actually run on a carrier.
    """
    import itertools
    from labs.common import LAB_DIRS
    from steganalysis import pipeline as P

    routed = set(itertools.chain.from_iterable(P.CONTAINER_LABS.values()))
    unrouted = set(LAB_DIRS) - routed
    assert unrouted == P.UNROUTED_BY_DESIGN, (
        f"labs neither routed nor declared an exception: "
        f"{sorted(unrouted - P.UNROUTED_BY_DESIGN)}")
    assert routed <= set(LAB_DIRS), "pipeline routes a lab that does not exist"


def test_pipeline_routes_every_carrier_family():
    """Eight carrier families were built after the pipeline and never wired in.

    A payload in a WAV went through the pipeline as E1 while lab 18 alone
    reached E4, because `container_kind` did not know RIFF and the unknown
    branch fell back to the PNG/JPEG structural labs. The blind capstone was
    therefore silent on half the carriers in the repository.
    """
    from steganalysis import pipeline as P
    from steganalysis.avi import VideoSpec, render_video
    from steganalysis.pcap import TrafficSpec, render_traffic
    from steganalysis.wav import AudioSpec, render_audio

    cases = {
        "png": corpus.render(corpus.CoverSpec("a.png", 1, 64, 64, "flat", "png")),
        "jpeg": corpus.render(corpus.CoverSpec("a.jpg", 1, 64, 64, "flat", "jpeg")),
        "wav": render_audio(AudioSpec("a.wav", 1)),
        "avi": render_video(VideoSpec("a.avi", 1, frames=4)),
        "pcap": render_traffic(TrafficSpec("a.pcap", 1, packets=20, seconds=2.0)),
        "text": b"The committee reviewed the submissions carefully.\n" * 8,
    }
    for expected, blob in cases.items():
        assert P.container_kind(blob) == expected, expected
        assert P.applicable_labs(blob), f"{expected} routes to no lab"


def test_pipeline_is_quiet_on_every_clean_carrier():
    """Routing a carrier somewhere must not manufacture a finding."""
    from steganalysis import pipeline as P
    from steganalysis.avi import VideoSpec, render_video
    from steganalysis.pcap import TrafficSpec, render_traffic
    from steganalysis.wav import AudioSpec, render_audio
    from steganalysis.evidence import Evidence

    for name, blob in [
        ("wav", render_audio(AudioSpec("a.wav", 3, silence_fraction=0.4))),
        ("avi", render_video(VideoSpec("a.avi", 3, frames=12))),
        ("pcap", render_traffic(TrafficSpec("a.pcap", 3, packets=400, seconds=30.0))),
        ("text", b"Ordinary prose with no joiners in it at all.\n" * 8),
    ]:
        assert P.analyse(blob, name).verdict == Evidence.E0, name


def test_a_lab_that_cannot_read_a_carrier_says_nothing():
    """Inapplicability is not a finding.

    Lab 01 reported E1 for any container whose end it could not compute, which
    flagged every clean WAV and AVI once those were routed through it.
    """
    from steganalysis.evidence import Evidence
    from steganalysis.wav import AudioSpec, render_audio
    lab = load_lab("01_trailing_data")
    assert lab.detect(render_audio(AudioSpec("a.wav", 5)), "a.wav",
                      baseline=None).verdict == Evidence.E0


def test_text_lab_accepts_bytes_from_the_pipeline():
    """Every lab receives bytes; lab 20 was written against str."""
    from steganalysis.evidence import Evidence
    lab = load_lab("20_text_unicode")
    prose = "The committee reviewed the submissions carefully. " * 6
    stego = lab.embed(prose, b"a payload long enough to form a run")
    assert lab.detect(stego.encode(), "s", baseline=None).verdict >= Evidence.E1
    # Undecodable input must produce no finding rather than an exception.
    assert lab.detect(b"\xff\xfe\x00\x01binary", "b",
                      baseline=None).verdict == Evidence.E0
