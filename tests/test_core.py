"""Core tests: parsers, the evidence ladder, corpus reproducibility, gates.

The evidence tests are the important ones. They assert that the library
*refuses* to record an unsupported verdict. If someone later softens
assert_reportable() into a warning to make a pipeline run, these go red.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis import corpus, jpeg as jpeg_mod, png as png_mod  # noqa: E402
from steganalysis.container import (bit_error_rate, classify_blob,  # noqa: E402
                                    lsb_extract, lsb_replace, parse_zip,
                                    shannon_entropy)
from steganalysis.evidence import (Evidence, FalsePositiveBaseline,  # noqa: E402
                                   Finding, Report, UnsupportedVerdict)


# ------------------------------------------------------------------ evidence

def _baseline(fp: int = 0, n: int = 100) -> FalsePositiveBaseline:
    return FalsePositiveBaseline("d", n, fp, 0.0, "test set")


def test_e3_without_baseline_raises():
    f = Finding(carrier="x", level=Evidence.E3, detector="d",
                claim="confirmed", domain="container")
    with pytest.raises(UnsupportedVerdict, match="without a false-positive baseline"):
        f.assert_reportable()


def test_e3_without_domain_raises():
    f = Finding(carrier="x", level=Evidence.E3, detector="d",
                claim="confirmed", baseline=_baseline())
    with pytest.raises(UnsupportedVerdict, match="embedding domain"):
        f.assert_reportable()


def test_e4_without_payload_raises():
    f = Finding(carrier="x", level=Evidence.E4, detector="d", claim="extracted",
                domain="container", baseline=_baseline())
    with pytest.raises(UnsupportedVerdict, match="no payload bytes"):
        f.assert_reportable()


def test_e1_needs_nothing():
    Finding(carrier="x", level=Evidence.E1, detector="d",
            claim="odd but explainable").assert_reportable()


def test_report_rejects_unsupported_finding():
    r = Report(carrier="x")
    with pytest.raises(UnsupportedVerdict):
        r.add(Finding(carrier="x", level=Evidence.E3, detector="d",
                      claim="confirmed", domain="container"))
    assert r.findings == []
    assert r.verdict == Evidence.E0


def test_verdict_is_the_maximum_level():
    r = Report(carrier="x")
    r.add(Finding(carrier="x", level=Evidence.E1, detector="a", claim="weak"))
    r.add(Finding(carrier="x", level=Evidence.E4, detector="b", claim="strong",
                  domain="container", payload=b"abc", baseline=_baseline()))
    assert r.verdict == Evidence.E4
    assert r.confirmed


def test_render_says_so_when_no_baseline_exists():
    f = Finding(carrier="x", level=Evidence.E1, detector="d", claim="weak")
    assert "NOT MEASURED" in f.render()


# ------------------------------------------------------------------- corpus

def test_corpus_is_byte_reproducible():
    spec = corpus.CoverSpec("r.png", 4242, 96, 64, "photo_like", "png")
    assert corpus.render(spec) == corpus.render(spec)


def test_corpus_specs_differ_by_seed():
    a = corpus.CoverSpec("a.png", 1, 96, 64, "texture", "png")
    b = corpus.CoverSpec("b.png", 2, 96, 64, "texture", "png")
    assert corpus.render(a) != corpus.render(b)


def test_manifest_round_trip(tmp_path):
    specs = corpus.default_specs()[:3]
    digests = corpus.write_corpus(specs, tmp_path / "c")
    corpus.write_manifest(specs, digests, tmp_path / "manifest.json")
    assert corpus.verify_manifest(tmp_path / "manifest.json", tmp_path / "c") == []
    # Tamper with one byte and the manifest must notice.
    victim = tmp_path / "c" / specs[0].name
    blob = bytearray(victim.read_bytes())
    blob[-1] ^= 0x01
    victim.write_bytes(bytes(blob))
    assert len(corpus.verify_manifest(tmp_path / "manifest.json", tmp_path / "c")) == 1


def test_manifest_records_the_toolchain():
    """A digest mismatch is unreadable without knowing what produced it."""
    assert set(corpus.toolchain()) == {"python", "Pillow", "zlib"}
    assert all(v for v in corpus.toolchain().values())


def test_manifest_drift_is_detected_against_the_stored_digests(tmp_path):
    """The check `--verify` structurally cannot do.

    `--verify` hashes files on disk against the manifest. When generate.py
    rewrote the manifest first, the two agreed by construction. This compares
    freshly rendered digests against what is stored, which is the only way
    drift away from the committed corpus becomes visible.
    """
    specs = corpus.default_specs()[:3]
    digests = corpus.write_corpus(specs, tmp_path / "c")
    manifest = tmp_path / "manifest.json"
    corpus.write_manifest(specs, digests, manifest)

    assert corpus.manifest_drift(manifest, digests) == []

    drifted = dict(digests)
    drifted[specs[0].name] = "0" * 64
    problems = corpus.manifest_drift(manifest, drifted)
    assert any(specs[0].name in p for p in problems)
    # Same toolchain, so the report must point at the renderer rather than
    # leaving the reader to guess between the two causes.
    assert any("UNCHANGED" in p for p in problems)


def test_manifest_drift_tolerates_a_manifest_without_a_toolchain(tmp_path):
    """v1.0.0 shipped before toolchain recording; it must still be checkable."""
    specs = corpus.default_specs()[:2]
    digests = corpus.write_corpus(specs, tmp_path / "c")
    manifest = tmp_path / "manifest.json"
    corpus.write_manifest(specs, digests, manifest)

    stripped = json.loads(manifest.read_text())
    del stripped["toolchain"]
    manifest.write_text(json.dumps(stripped))

    assert corpus.manifest_drift(manifest, digests) == []
    problems = corpus.manifest_drift(manifest, {**digests, specs[0].name: "0" * 64})
    assert any("predates toolchain recording" in p for p in problems)



def test_difftest_finds_the_binary_under_either_platform_name(tmp_path):
    """Windows emits stegscan.exe; looking only for the bare name reported
    that cargo was unavailable on a machine that had just built the crate."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib
    difftest = importlib.import_module("difftest")

    assert difftest.find_binary(tmp_path) is None
    (tmp_path / "stegscan.exe").write_bytes(b"")
    assert difftest.find_binary(tmp_path).name == "stegscan.exe"
    (tmp_path / "stegscan").write_bytes(b"")
    assert difftest.find_binary(tmp_path).name == "stegscan"


# ---------------------------------------------------------------- png parser

def test_png_chunk_property_bits():
    """The four type letters encode four different things."""
    blob = corpus.render(corpus.CoverSpec("p.png", 5, 64, 48, "flat", "png"))
    parsed = png_mod.parse_png(blob)
    ihdr = parsed.chunks_of("IHDR")[0]
    assert not ihdr.is_ancillary and not ihdr.is_private
    assert ihdr.reserved_bit_ok and not ihdr.is_safe_to_copy

    body = b"payload"
    chunk = (struct.pack(">I", len(body)) + b"stEG" + body
             + struct.pack(">I", zlib.crc32(b"stEG" + body) & 0xFFFFFFFF))
    c = png_mod.parse_png(blob[:ihdr.offset] + chunk + blob[ihdr.offset:]).chunks[0]
    assert c.ctype == "stEG"
    assert c.is_ancillary          # letter 1 lowercase
    assert c.is_private            # letter 2 lowercase -- NOT letter 3
    assert c.reserved_bit_ok       # letter 3 uppercase
    assert not c.is_safe_to_copy   # letter 4 uppercase


def test_png_truncation_is_an_error_not_an_exception():
    blob = corpus.render(corpus.CoverSpec("p.png", 6, 64, 48, "flat", "png"))
    parsed = png_mod.parse_png(blob[:len(blob) // 2])
    assert parsed.errors
    assert parsed.iend_end is None


def test_png_bad_magic():
    assert png_mod.parse_png(b"not a png at all").errors == ["missing PNG signature"]


# --------------------------------------------------------------- jpeg parser

def test_jpeg_scan_walk_honours_byte_stuffing():
    blob = corpus.render(corpus.CoverSpec("j.jpg", 7, 128, 96, "photo_like",
                                          "jpeg", quality=95))
    parsed = jpeg_mod.parse_jpeg(blob)
    assert parsed.errors == []
    assert parsed.eoi_end == len(blob)
    scan = parsed.scans[0]
    # Stuffed 0xFF00 pairs inside the scan must not have terminated it.
    assert scan.stuffed_ff > 0
    assert scan.end == len(blob) - 2


def test_jpeg_decode_scan_consumes_exactly_the_scan():
    blob = corpus.render(corpus.CoverSpec("j.jpg", 8, 128, 96, "texture",
                                          "jpeg", quality=88))
    parsed = jpeg_mod.parse_jpeg(blob)
    d = jpeg_mod.decode_scan(parsed, collect_coefficients=True)
    assert d.supported, d.reason
    assert d.mcus_decoded == d.mcus_expected
    assert d.surplus == 0
    assert set(d.coefficients) == {1, 2, 3}
    assert d.coefficients[1].shape[1] == 64


def test_jpeg_progressive_matches_baseline_coefficients():
    """Gap G-6, closed. The validation is an identity, not a tolerance.

    The same image saved baseline and progressive at one quality shares its
    quantisation tables, so the DCT coefficients are the same numbers sent in a
    different order. Any disagreement is a decoder bug, and the check is exact.
    """
    import io
    from PIL import Image
    for quality, side in ((90, 128), (75, 192)):
        spec = corpus.CoverSpec("t.jpg", quality, side, side * 3 // 4,
                                "photo_like", "jpeg", quality=quality)
        gray = np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))
        flat, prog = io.BytesIO(), io.BytesIO()
        Image.fromarray(gray, mode="L").save(flat, format="JPEG", quality=quality)
        Image.fromarray(gray, mode="L").save(prog, format="JPEG",
                                             quality=quality, progressive=True)
        jb = jpeg_mod.parse_jpeg(flat.getvalue())
        jp = jpeg_mod.parse_jpeg(prog.getvalue())
        assert jb.quant_tables() == jp.quant_tables()
        assert len(jp.scans) > 1, "expected a multi-scan progressive file"
        db = jpeg_mod.decode_scan(jb, collect_coefficients=True)
        dp = jpeg_mod.decode_scan(jp, collect_coefficients=True)
        assert db.supported and dp.supported, (db.reason, dp.reason)
        assert np.array_equal(db.coefficients[1], dp.coefficients[1])


def test_jpeg_dc_matches_an_independent_computation():
    """Neither decoder is the reference; the pixels are.

    Two decoders agreeing proves nothing if they share a bug -- and during
    development they did, in a form that also survived the encoder round-trip,
    because encode and decode used the same wrong convention and reproduced the
    file byte for byte. The DC computed straight from the decoded pixels breaks
    that circle.
    """
    import io
    from PIL import Image
    from scipy.fftpack import dctn
    spec = corpus.CoverSpec("t.jpg", 7, 128, 96, "photo_like", "jpeg", quality=90)
    gray = np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))
    buf = io.BytesIO()
    Image.fromarray(gray, mode="L").save(buf, format="JPEG", quality=90)
    parsed = jpeg_mod.parse_jpeg(buf.getvalue())
    decoded = jpeg_mod.decode_scan(parsed, collect_coefficients=True)
    pixels = np.array(Image.open(io.BytesIO(buf.getvalue())).convert("L"))
    q0 = parsed.quant_tables()[0][0]
    for i in range(4):
        block = pixels[0:8, i * 8:(i + 1) * 8].astype(np.float64) - 128.0
        expected = dctn(block, norm="ortho")[0, 0] / q0
        assert abs(decoded.coefficients[1][i, 0] - expected) < 1.0, i

def test_strip_to_eoi_removes_trailing():
    blob = corpus.render(corpus.CoverSpec("j.jpg", 10, 96, 64, "flat", "jpeg"))
    assert jpeg_mod.strip_to_eoi(blob + b"XXXX") == blob


# ----------------------------------------------------------------- container

def test_lsb_round_trip_sequential_and_seeded():
    import numpy as np
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)
    payload = b"container round trip payload"
    assert lsb_extract(lsb_replace(arr, payload), len(payload)) == payload
    assert lsb_extract(lsb_replace(arr, payload, seed=99), len(payload), seed=99) == payload


def test_lsb_wrong_seed_recovers_noise():
    import numpy as np
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
    payload = b"A" * 64
    stego = lsb_replace(arr, payload, seed=1)
    wrong = lsb_extract(stego, len(payload), seed=2)
    assert bit_error_rate(payload, wrong) > 0.30


def test_entropy_and_classification():
    assert shannon_entropy(b"") == 0.0
    assert shannon_entropy(b"\x00" * 1000) == 0.0
    assert classify_blob(b"hello world, this is plain text\n" * 4) == "text"
    assert classify_blob(b"PK\x03\x04rest") == "zip-header"
    assert classify_blob(b"\x00" * 512) == "low-entropy-padding"


def test_zip_gap_accounting():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", b"aaa")
    clean = buf.getvalue()
    assert parse_zip(clean).gaps == []


# --------------------------------------------------------------------- gates

@pytest.mark.slow
def test_gate_g0_passes():
    proc = subprocess.run([sys.executable, str(ROOT / "gates" / "g0_wardens.py")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    results = json.loads((ROOT / "gates" / "results" / "G0.json").read_text())
    by_name = {r["name"]: r for r in results}
    assert by_name["A_passive_channel_is_lossless"]["max_ber"] == 0.0
    assert by_name["B1_active_warden_destroys_lsb"]["median_ber"] > 0.45


@pytest.mark.slow
def test_gate_g1_passes():
    proc = subprocess.run([sys.executable, str(ROOT / "gates" / "g1_parsers.py")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    results = json.loads((ROOT / "gates" / "results" / "G1.json").read_text())
    by_name = {r["name"]: r for r in results}
    if by_name["A_png_matches_pngcheck"].get("pass") is not None:
        assert by_name["A_png_matches_pngcheck"]["mismatch_count"] == 0
    if by_name["B_jpeg_matches_djpeg"].get("pass") is not None:
        assert by_name["B_jpeg_matches_djpeg"]["mismatch_count"] == 0


# ------------------------------------------- SPA applicability (G-11)

def test_spa_asymmetry_reports_synthetic_covers_as_inapplicable():
    """The measurement that decides whether SPA has anything to estimate from.

    Every trace-set equation collapses to an identity when the cover's LSBs are
    unbiased -- (X+Y)/Z measures 1.00 across trace sets, which is just
    P(lu=lv)=1/2 and holds in the stego too. The asymmetry can only live at
    m=0, where the LSB pattern is forced by the difference. On these synthetic
    covers it does not: the odd fraction sits at 1/2 and the coefficient the
    estimator would divide by is a rounding error.
    """
    import io
    from PIL import Image
    from steganalysis.detectors import spa_asymmetry
    spec = corpus.CoverSpec("g.png", 9_300_001, 256, 256, "photo_like", "png")
    gray = np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))
    report = spa_asymmetry(gray)
    assert 0.45 < report["m0_odd_fraction"] < 0.55
    assert abs(report["m0_coefficient"]) < 0.05 * report["m0_pairs"]
    assert report["applicable"] is False


def test_spa_trace_set_size_is_invariant_under_embedding():
    """The one property the whole trace-set model rests on."""
    import io
    from PIL import Image
    from steganalysis import embedders as E
    from steganalysis.detectors import spa_trace_counts
    spec = corpus.CoverSpec("g.png", 9_300_002, 192, 192, "texture", "png")
    cover = np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))
    stego = E.lsb_replacement(cover, 1.0, seed=1).stego
    a, b = spa_trace_counts(cover), spa_trace_counts(stego)
    total_a = a["X"] + a["Y"] + a["Z00"] + a["Z11"]
    total_b = b["X"] + b["Y"] + b["Z00"] + b["Z11"]
    assert np.array_equal(total_a, total_b)


# ------------------------------------------------ Sample Pair Analysis (G-11)

def test_spa_estimates_the_payload_length():
    """Dumitrescu-Wu-Wang equation (18), implemented from the paper.

    Three reconstructions from memory failed before this one, all in the same
    way: the trace sets were defined by LSB pattern instead of by which
    component of a pair is larger, which makes every equation an identity.
    """
    import io
    from PIL import Image
    from steganalysis import embedders as E
    from steganalysis.detectors import sample_pair_analysis

    spec = corpus.CoverSpec("g.png", 9_990_001, 256, 256, "photo_like", "png")
    cover = np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))

    assert sample_pair_analysis(cover).value < 0.05
    for rate in (0.05, 0.10, 0.20, 0.40):
        stego = E.lsb_replacement(cover, rate, seed=1).stego
        assert abs(sample_pair_analysis(stego).value - rate) < 0.03, rate


def test_spa_stays_flat_on_lsb_matching():
    """A required failure: matching creates no even/odd asymmetry to measure."""
    import io
    from PIL import Image
    from steganalysis import embedders as E
    from steganalysis.detectors import sample_pair_analysis

    spec = corpus.CoverSpec("g.png", 9_990_002, 256, 256, "texture", "png")
    cover = np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))
    clean = sample_pair_analysis(cover).value
    matched = sample_pair_analysis(E.lsb_matching(cover, 0.4, seed=1).stego).value
    assert abs(matched - clean) < 0.05


def test_spa_trace_sets_are_defined_by_magnitude_not_parity():
    """The definition the failed reconstructions got wrong.

    X and Y split pairs of odd difference by WHICH COMPONENT IS LARGER, not by
    LSB pattern. Splitting by parity makes X = Y identically and the estimator
    reads zero on everything.
    """
    from steganalysis import embedders as E
    from steganalysis.detectors import sample_pair_analysis
    rng = np.random.default_rng(0)
    walk = np.cumsum(rng.normal(0, 3.0, 200 * 200)) + 128.0
    cover = np.clip(walk - np.floor(walk / 256) * 256, 0, 255
                    ).astype(np.uint8).reshape(200, 200)
    stego = E.lsb_replacement(cover, 0.3, seed=2).stego
    assert sample_pair_analysis(stego).value > sample_pair_analysis(cover).value + 0.1
