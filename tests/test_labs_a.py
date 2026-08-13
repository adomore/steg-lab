"""A-group lab tests.

Each lab must satisfy two conditions, and the second is the one that has
teeth:

  1. It detects its own stego carrier and recovers the payload.
  2. It stays silent on 100 same-source clean covers.

A detector that only satisfies (1) is a detector that says "yes" to
everything. Condition (2) is a false-positive rate measured in the test
suite, so a regression that makes a detector trigger-happy turns the bar
red rather than quietly inflating everyone's findings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab, measure_baseline, payload_blob  # noqa: E402
from steganalysis import corpus  # noqa: E402
from steganalysis.evidence import Evidence, UnsupportedVerdict  # noqa: E402

N_CLEAN = 100


@pytest.fixture(scope="module")
def png_cover() -> bytes:
    return corpus.render(corpus.CoverSpec("t.png", 11_001, 192, 128, "photo_like", "png"))


@pytest.fixture(scope="module")
def jpeg_cover() -> bytes:
    return corpus.render(corpus.CoverSpec("t.jpg", 11_002, 192, 128, "photo_like",
                                          "jpeg", quality=92))


# ---------------------------------------------------------------- lab 01

def test_lab01_detects_trailing_png(png_cover):
    lab = load_lab("01_trailing_data")
    payload = payload_blob("lab01-png")
    stego = lab.embed(png_cover, payload)
    baseline = measure_baseline(lab.detect, "trailing_data", N_CLEAN, "png", 310_000)
    report = lab.detect(stego, "stego.png", baseline=baseline)

    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == payload
    assert report.findings[0].payload_offset == len(png_cover)


def test_lab01_detects_trailing_jpeg(jpeg_cover):
    lab = load_lab("01_trailing_data")
    payload = payload_blob("lab01-jpg")
    stego = lab.embed(jpeg_cover, payload)
    baseline = measure_baseline(lab.detect, "trailing_data", N_CLEAN, "jpeg", 311_000)
    report = lab.detect(stego, "stego.jpg", baseline=baseline)

    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == payload


@pytest.mark.parametrize("fmt,seed", [("png", 312_000), ("jpeg", 313_000)])
def test_lab01_zero_false_positives(fmt, seed):
    lab = load_lab("01_trailing_data")
    baseline = measure_baseline(lab.detect, "trailing_data", N_CLEAN, fmt, seed)
    assert baseline.n_false_positives == 0, baseline.describe()


# ---------------------------------------------------------------- lab 02

def test_lab02_polyglot_is_a_valid_archive(png_cover):
    lab = load_lab("02_polyglot")
    stego = lab.embed(png_cover, [("flag.txt", b"lab02 polyglot payload\n")])

    # Still a PNG...
    from steganalysis import png as png_mod
    assert png_mod.parse_png(stego).errors == []
    # ...and simultaneously a ZIP.
    assert lab.opens_as_zip(stego) == ["flag.txt"]

    baseline = measure_baseline(lab.detect, "polyglot_zip", N_CLEAN, "png", 320_000)
    report = lab.detect(stego, "polyglot.png", baseline=baseline)
    assert report.verdict == Evidence.E4


def test_lab02_zero_false_positives():
    """The strong detector is clean; the weak one is not, and that is the point."""
    lab = load_lab("02_polyglot")

    # Structural check: a file either opens as an archive or it does not.
    strong = measure_baseline(lab.detect, "polyglot_zip", N_CLEAN, "png", 321_000)
    assert strong.n_false_positives == 0, strong.describe()

    # Bare signature scan: compressed pixel data contains arbitrary bytes, so
    # "PK\x03\x04" turns up by chance. Measured, not assumed -- this is exactly
    # why a signature hit is capped at E1 and never counts as a verdict.
    weak = measure_baseline(lab.detect, "polyglot_signature_scan",
                            N_CLEAN, "png", 321_000)
    assert weak.n_false_positives > 0, (
        "expected chance signature hits in compressed data; if this ever "
        "reaches zero the clean set is too small to make the point")
    assert weak.fpr < 0.20, weak.describe()


# ---------------------------------------------------------------- lab 03

def test_lab03_png_text_chunk(png_cover):
    lab = load_lab("03_metadata")
    payload = payload_blob("lab03-text")
    stego = lab.embed(png_cover, payload)
    baseline = measure_baseline(lab.detect, "metadata_profile", N_CLEAN, "png", 330_000)
    report = lab.detect(stego, "meta.png", baseline=baseline)

    assert report.verdict == Evidence.E4
    assert any(f.payload == payload for f in report.findings)


def test_lab03_png_compressed_text_chunk(png_cover):
    lab = load_lab("03_metadata")
    payload = payload_blob("lab03-ztxt")
    stego = lab.embed_png(png_cover, payload, compressed=True)
    baseline = measure_baseline(lab.detect, "metadata_profile", N_CLEAN, "png", 331_000)
    report = lab.detect(stego, "meta_z.png", baseline=baseline)
    assert any(f.payload == payload for f in report.findings)


def test_lab03_jpeg_comment(jpeg_cover):
    lab = load_lab("03_metadata")
    payload = payload_blob("lab03-jpg")
    stego = lab.embed(jpeg_cover, payload)
    baseline = measure_baseline(lab.detect, "metadata_profile", N_CLEAN, "jpeg", 332_000)
    report = lab.detect(stego, "meta.jpg", baseline=baseline)
    assert any(f.payload == payload for f in report.findings)


@pytest.mark.parametrize("fmt,seed", [("png", 333_000), ("jpeg", 334_000)])
def test_lab03_zero_false_positives(fmt, seed):
    lab = load_lab("03_metadata")
    baseline = measure_baseline(lab.detect, "metadata_profile", N_CLEAN, fmt, seed)
    assert baseline.n_false_positives == 0, baseline.describe()


# ---------------------------------------------------------------- lab 04

def test_lab04_private_chunk(png_cover):
    lab = load_lab("04_png_chunks")
    payload = payload_blob("lab04-private")
    stego = lab.embed(png_cover, payload, variant="private_chunk")
    baseline = measure_baseline(lab.detect, "png_unknown_chunk", N_CLEAN, "png", 340_000)
    report = lab.detect(stego, "priv.png", baseline=baseline)

    assert report.verdict == Evidence.E4
    assert any(f.payload == payload for f in report.findings)


def test_lab04_stale_crc(png_cover):
    lab = load_lab("04_png_chunks")
    stego = lab.embed(png_cover, b"OVERWRITTEN-BYTES", variant="stale_crc")
    baseline = measure_baseline(lab.detect, "png_crc_mismatch", N_CLEAN, "png", 341_000)
    report = lab.detect(stego, "crc.png", baseline=baseline)

    assert any(f.detector == "png_crc_mismatch" for f in report.findings)


def test_lab04_height_truncation_is_invisible_to_everything_else(png_cover):
    """The point of this variant: nothing else fires, and the PNG is legal."""
    lab04 = load_lab("04_png_chunks")
    lab01 = load_lab("01_trailing_data")
    stego = lab04.embed(png_cover, b"", variant="height_truncation")

    from steganalysis import png as png_mod
    parsed = png_mod.parse_png(stego)
    assert parsed.errors == []
    assert not parsed.bad_crc_chunks()          # every CRC is valid
    assert parsed.trailing == b""               # nothing appended

    b1 = measure_baseline(lab01.detect, "trailing_data", 20, "png", 342_500)
    assert lab01.detect(stego, "trunc.png", baseline=b1).verdict == Evidence.E0

    baseline = measure_baseline(lab04.detect, "png_height_truncation",
                                N_CLEAN, "png", 342_000)
    report = lab04.detect(stego, "trunc.png", baseline=baseline)
    hits = [f for f in report.findings if f.detector == "png_height_truncation"]
    assert len(hits) == 1
    assert hits[0].detail["true_height"] == hits[0].detail["declared_height"] + 40

    restored = lab04.recover_true_height(stego)
    assert restored is not None
    restored_parsed = png_mod.parse_png(restored)
    assert restored_parsed.ihdr.height == hits[0].detail["true_height"]


def test_lab04_zero_false_positives():
    lab = load_lab("04_png_chunks")
    baseline = measure_baseline(lab.detect, "png_chunks", N_CLEAN, "png", 343_000)
    assert baseline.n_false_positives == 0, baseline.describe()


# ---------------------------------------------------------------- lab 05

def test_lab05_pseudo_encryption():
    lab = load_lab("05_zip_structure")
    stego = lab.build_sample(b"", variant="pseudo_encryption")
    baseline = measure_baseline(lab.detect, "zip_pseudo_encryption",
                                N_CLEAN, "png", 350_000)
    report = lab.detect(stego, "pseudo.zip", baseline=baseline)

    hits = [f for f in report.findings if f.detector == "zip_pseudo_encryption"]
    assert len(hits) == 2                       # both entries flagged
    assert report.verdict >= Evidence.E3


def test_lab05_archive_comment():
    lab = load_lab("05_zip_structure")
    payload = payload_blob("lab05-comment")
    stego = lab.build_sample(payload, variant="comment")
    baseline = measure_baseline(lab.detect, "zip_archive_comment",
                                N_CLEAN, "png", 351_000)
    report = lab.detect(stego, "comment.zip", baseline=baseline)
    assert any(f.payload == payload for f in report.findings)


def test_lab05_gap_stays_readable():
    lab = load_lab("05_zip_structure")
    payload = payload_blob("lab05-gap")
    stego = lab.build_sample(payload, variant="gap")

    # A hiding place that breaks the archive is not a hiding place.
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(stego)) as zf:
        assert zf.testzip() is None
        assert sorted(zf.namelist()) == ["data.bin", "readme.txt"]

    baseline = measure_baseline(lab.detect, "zip_unreferenced_gap",
                                N_CLEAN, "png", 352_000)
    report = lab.detect(stego, "gap.zip", baseline=baseline)
    hits = [f for f in report.findings if f.detector == "zip_unreferenced_gap"]
    assert hits and hits[0].payload == payload


def test_lab05_clean_archive_is_clean():
    lab = load_lab("05_zip_structure")
    clean = lab.make_archive()
    assert lab.detect(clean, "clean.zip", baseline=None).verdict == Evidence.E0


# ---------------------------------------------------------------- lab 06

@pytest.mark.parametrize("variant,detector", [
    ("comment", "jpeg_comment_segment"),
    ("rogue_appn", "jpeg_rogue_appn"),
    ("post_scan", "jpeg_scan_surplus"),
])
def test_lab06_variants(jpeg_cover, variant, detector):
    lab = load_lab("06_jpeg_segments")
    payload = payload_blob(f"lab06-{variant}")
    stego = lab.embed(jpeg_cover, payload, variant=variant)

    # The carrier must still decode as an image.
    import io
    from PIL import Image
    Image.open(io.BytesIO(stego)).load()

    baseline = measure_baseline(lab.detect, detector, N_CLEAN, "jpeg", 360_000)
    report = lab.detect(stego, f"{variant}.jpg", baseline=baseline)
    hits = [f for f in report.findings if f.detector == detector]
    assert hits, f"{detector} did not fire on variant {variant}"
    assert report.verdict == Evidence.E4


def test_lab06_zero_false_positives():
    lab = load_lab("06_jpeg_segments")
    baseline = measure_baseline(lab.detect, "jpeg_segments", N_CLEAN, "jpeg", 361_000)
    assert baseline.n_false_positives == 0, baseline.describe()


def test_lab06_scan_walk_beats_naive_eoi_search(jpeg_cover):
    """A naive 0xFFD9 search finds a false EOI inside compressed data.

    This is the concrete justification for reimplementing the scan walk.
    If this test ever passes trivially (no false hit in the sample), the
    sample is too small to make the point and should be enlarged.
    """
    from steganalysis import jpeg as jpeg_mod
    parsed = jpeg_mod.parse_jpeg(jpeg_cover)
    true_eoi = parsed.eoi_end - 2
    scan = parsed.scans[-1]
    naive = jpeg_cover.find(b"\xff\xd9")
    assert true_eoi == len(jpeg_cover) - 2
    assert scan.end == true_eoi
    if naive != true_eoi:
        assert naive < scan.end, "naive search should hit inside the scan"
