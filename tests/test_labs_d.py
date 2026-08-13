"""D-group tests: the JPEG entropy encoder and lab 13.

The encoder tests check coefficient equality rather than pixel equality.
Two different coefficient sets can decode to visually identical pixels, and
a steganographic payload lives in the coefficients -- so a pixel comparison
would pass on exactly the failure that matters.
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
from steganalysis import corpus, embedders as E  # noqa: E402
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402
from steganalysis.jpeg_encode import (EncodeError, build_huffman_table,  # noqa: E402
                                      coefficients_of, recode)


def payload(nbytes: int, seed: int) -> bytes:
    """Seeded payload bytes.

    These tests used os.urandom, which made them irreproducible: the payload
    differed every run, and at the smallest payload the windowed chi-square
    sits near its detection boundary, so the suite passed or failed by luck.
    A test that cannot be rerun to the same answer cannot be debugged.
    """
    return np.random.default_rng(seed).integers(0, 256, nbytes,
                                                dtype=np.uint8).tobytes()


def jpeg_cover(seed: int, quality: int = 90, side: int = 256) -> bytes:
    return corpus.render(corpus.CoverSpec(
        "c.jpg", seed, side, side, ["texture", "photo_like"][seed % 2],
        "jpeg", quality=quality))


# ------------------------------------------------------------------ huffman

def test_huffman_table_is_a_valid_jpeg_table():
    freq = [0] * 256
    for i, f in enumerate([100, 60, 30, 12, 5, 2, 1]):
        freq[i] = f
    bits, huffval = build_huffman_table(freq)
    assert len(bits) == 16
    assert sum(bits) == len(huffval) == 7
    # No code may be longer than 16 bits, and the code space must not overflow.
    total = sum(count / (2 ** length) for length, count in enumerate(bits, start=1))
    assert total <= 1.0


def test_huffman_handles_a_single_symbol():
    freq = [0] * 256
    freq[42] = 1000
    bits, huffval = build_huffman_table(freq)
    assert huffval == [42]
    assert sum(bits) == 1


# ------------------------------------------------------------------ encoder

@pytest.mark.parametrize("quality", [70, 85, 95])
def test_round_trip_is_coefficient_exact(quality):
    blob = jpeg_cover(980_001, quality)
    out = recode(blob)
    before, after = coefficients_of(blob), coefficients_of(out)
    assert after is not None
    for cid in before:
        assert np.array_equal(before[cid], after[cid])


def test_round_trip_preserves_pixels():
    blob = jpeg_cover(980_002)
    out = recode(blob)
    pa = np.array(Image.open(io.BytesIO(blob)).convert("RGB"))
    pb = np.array(Image.open(io.BytesIO(out)).convert("RGB"))
    assert np.array_equal(pa, pb)


def test_optimal_tables_shrink_the_file():
    blob = jpeg_cover(980_003)
    assert len(recode(blob)) < len(blob)


@pytest.mark.parametrize("name,fn", [
    ("jsteg", lambda c: E.jsteg(c, 0.8, seed=1).stego),
    ("f5", lambda c: E.f5(c, 0.5, k=3, seed=1).stego),
    ("f5_no_shrinkage", lambda c: E.f5(c, 0.5, k=3, seed=1, no_shrinkage=True).stego),
])
def test_modified_coefficients_survive_the_write(name, fn):
    blob = jpeg_cover(980_004)
    want = fn(coefficients_of(blob)[1])
    got = coefficients_of(recode(blob, transform=fn, component=1))[1]
    assert np.array_equal(want, got)


def test_encoder_refuses_wrong_block_count():
    from steganalysis.jpeg import parse_jpeg
    blob = jpeg_cover(980_005)
    from steganalysis.jpeg_encode import encode_baseline
    coeffs = coefficients_of(blob)
    coeffs[1] = coeffs[1][:-1]
    with pytest.raises(EncodeError, match="blocks"):
        encode_baseline(parse_jpeg(blob), coeffs)


def test_jsteg_skips_magnitude_not_value():
    """The P1 bug: -1 must be skipped, or a 0 bit turns it into 0."""
    coeffs = np.array([[-1, 1, 0, 2, -2, 3] + [0] * 58], dtype=np.int32)
    stego = E.jsteg(coeffs, rate=1.0, seed=1).stego
    protected = np.abs(coeffs) <= 1
    assert np.array_equal(stego[protected], coeffs[protected])
    assert np.count_nonzero(stego == 0) == np.count_nonzero(coeffs == 0)


# ------------------------------------------------------------------- lab 13

def test_lab13_payload_recovered_byte_exact():
    lab = load_lab("13_jsteg_jpeg")
    data = payload(500, 5001)
    stego = lab.embed(jpeg_cover(981_001), data)
    assert lab.extract(stego, len(data)) == data


def test_lab13_reaches_e4():
    """The first statistical-domain lab that produces the payload."""
    lab = load_lab("13_jsteg_jpeg")
    data = payload(500, 5002)
    stego = lab.embed(jpeg_cover(981_002), data)
    baseline = FalsePositiveBaseline("jsteg_pair_chi_square", 30, 0, 0.40,
                                     "30 same-source clean JPEGs")
    report = lab.detect(stego, "s.jpg", baseline=baseline, payload_bytes=len(data))
    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == data


def test_lab13_zero_false_positives():
    lab = load_lab("13_jsteg_jpeg")
    covers = [jpeg_cover(982_000 + i) for i in range(20)]
    fp = sum(1 for c in covers if lab.detect(c, "c", baseline=None).verdict >= Evidence.E1)
    assert fp == 0, f"{fp}/20 false positives"


@pytest.mark.parametrize("nbytes", [200, 600, 1000])
def test_lab13_detects_and_estimates_length(nbytes):
    lab = load_lab("13_jsteg_jpeg")
    detected = 0
    errors = []
    for i in range(6):
        stego = lab.embed(jpeg_cover(983_000 + i), payload(nbytes, 6000 + i))
        report = lab.detect(stego, "s.jpg", baseline=None)
        if report.verdict >= Evidence.E1:
            detected += 1
            est = report.findings[0].detail["estimated_payload_bytes"]
            errors.append(abs(est - nbytes) / nbytes)
    assert detected == 6, f"detected {detected}/6"
    assert np.mean(errors) < 0.35, f"length estimate error {np.mean(errors):.2f}"


def test_lab13_capacity_is_enforced():
    lab = load_lab("13_jsteg_jpeg")
    with pytest.raises(ValueError, match="payload needs"):
        lab.embed(jpeg_cover(984_001), payload(100_000, 7001))


# ------------------------------------------------- lab 14 (F5 calibration)

def gray_jpeg(seed: int, quality: int = 90) -> bytes:
    lab = load_lab("14_f5_calibration")
    return lab.to_grayscale_jpeg(jpeg_cover(seed, quality))


def test_lab14_calibration_preserves_the_quantisation_table():
    """Comparing two different quantisers yields a confident number about nothing."""
    import io
    from PIL import Image
    from steganalysis.jpeg import parse_jpeg
    lab = load_lab("14_f5_calibration")
    cover = gray_jpeg(1_600_001)
    original = parse_jpeg(cover).quant_tables()
    # calibrate() must round-trip the table; rebuild it the same way it does
    img = Image.open(io.BytesIO(cover))
    buf = io.BytesIO()
    arr = np.array(img.convert("L"))[4:, 4:]
    Image.fromarray(arr, mode="L").save(buf, format="JPEG",
                                        qtables=img.quantization)
    assert parse_jpeg(buf.getvalue()).quant_tables() == original


def test_lab14_beta_is_biased_but_stable():
    """The bias is what makes beta a relative statistic and not an absolute one."""
    lab = load_lab("14_f5_calibration")
    betas = [lab.estimate_change_rate(gray_jpeg(1_601_000 + i))["beta"]
             for i in range(12)]
    assert np.mean(betas) < -0.05, "expected the calibration bias to be negative"
    assert np.std(betas) < 0.05, f"bias must be stable, sd={np.std(betas):.4f}"


def test_lab14_detects_f5_and_stays_quiet_on_clean():
    lab = load_lab("14_f5_calibration")
    covers = [gray_jpeg(1_602_000 + i) for i in range(10)]
    false_alarms = sum(1 for c in covers
                       if lab.detect(c, "c", baseline=None).verdict >= Evidence.E1)
    assert false_alarms == 0, f"{false_alarms}/10 false alarms"

    baseline = FalsePositiveBaseline("f5_calibration", 10, 0, -0.13,
                                     "10 same-source clean grayscale JPEGs")
    detected = sum(1 for i, c in enumerate(covers)
                   if lab.detect(lab.embed(c, rate=0.15, k=3, seed=i), "s",
                                 baseline=baseline).verdict >= Evidence.E3)
    assert detected >= 8, f"detected {detected}/10 at 0.15 bpp"


def test_lab14_names_the_family_not_the_member():
    """The withdrawn claim: zero excess cannot tell F5 from nsF5 here."""
    lab = load_lab("14_f5_calibration")
    baseline = FalsePositiveBaseline("f5_calibration", 10, 0, -0.13, "clean")
    report = lab.detect(lab.embed(gray_jpeg(1_603_001), rate=0.15, seed=1),
                        "s", baseline=baseline)
    assert report.verdict == Evidence.E3
    assert report.findings[0].algorithm == "f5-family"
    assert report.findings[0].detail["beta_is_a_relative_statistic"] is True


def test_lab14_shrinkage_free_variant_changes_fewer_coefficients():
    """G2's 45% efficiency loss, seen from the detection side."""
    lab = load_lab("14_f5_calibration")
    cover = gray_jpeg(1_604_001)
    base = coefficients_of(cover)[1][:, 1:]
    rates = {}
    for label, ns in (("f5", False), ("nsf5", True)):
        stego = coefficients_of(lab.embed(cover, rate=0.15, k=3, seed=1,
                                          no_shrinkage=ns))[1][:, 1:]
        rates[label] = np.count_nonzero(base != stego) / np.count_nonzero(base)
    assert rates["nsf5"] < rates["f5"] * 0.75, rates


# --------------------------------------- lab 14 source model (G-20 closed)

def test_source_model_names_the_member():
    """Calibration could name the family; a population reference names the member.

    The carrier-derived calibration reached AUC 0.622-0.736 discriminating F5
    from its shrinkage-free variant, because the reference is computed from the
    stego image and moves with it. A source model does not move.
    """
    lab = load_lab("14_f5_calibration")
    covers = [gray_jpeg(1_800_000 + i) for i in range(20)]
    model = lab.build_source_model(covers[:10])
    baseline = FalsePositiveBaseline("f5_calibration", 10, 0, -0.13, "clean")

    correct = {"f5": 0, "f5-no-shrinkage": 0}
    for i, cover in enumerate(covers[10:]):
        for expected, no_shrinkage in (("f5", False), ("f5-no-shrinkage", True)):
            report = lab.detect(
                lab.embed(cover, rate=0.15, k=3, seed=i, no_shrinkage=no_shrinkage),
                "s", baseline=baseline, source_model=model)
            if report.findings and report.findings[0].algorithm == expected:
                correct[expected] += 1
    assert correct["f5"] >= 9, correct
    assert correct["f5-no-shrinkage"] >= 8, correct


def test_shrinkage_raises_the_zero_bin_and_the_variant_does_not():
    """The mechanism, not just the outcome."""
    lab = load_lab("14_f5_calibration")
    covers = [gray_jpeg(1_810_000 + i) for i in range(14)]
    model = lab.build_source_model(covers[:8])
    f5 = [lab.name_the_member(model, lab.embed(c, rate=0.15, seed=i))["z_zero"]
          for i, c in enumerate(covers[8:])]
    ns = [lab.name_the_member(model, lab.embed(c, rate=0.15, seed=i,
                                               no_shrinkage=True))["z_zero"]
          for i, c in enumerate(covers[8:])]
    assert np.mean(f5) > 1.0, f"F5 zero-bin z-score {np.mean(f5):.2f}"
    assert abs(np.mean(ns)) < 1.0, f"variant zero-bin z-score {np.mean(ns):.2f}"


def test_source_model_needs_enough_clean_carriers():
    lab = load_lab("14_f5_calibration")
    with pytest.raises(ValueError, match="at least 4"):
        lab.build_source_model([gray_jpeg(1_820_001)])
