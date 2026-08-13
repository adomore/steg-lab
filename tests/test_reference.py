"""Tests for the reference-corpus loader.

BOSSbase is not in this repository and never will be, so these tests run
against a stand-in with BOSSbase's exact on-disk shape -- 512x512 8-bit P5
PGM named 1.pgm..N.pgm, as a directory and as a zip. The FORMAT is real; the
pixel content is not, which is exactly why the photographic-content check
exists and is tested here.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis.reference import (BOSSBASE_CAMERAS_UNVERIFIED,  # noqa: E402
                                    CorpusError, discover, find_bossbase,
                                    read_pgm, verify)

HDR = b"P5\n512 512\n255\n"


def _pgm(arr: np.ndarray) -> bytes:
    h, w = arr.shape
    return f"P5\n{w} {h}\n255\n".encode() + arr.tobytes()


def _photographic(seed: int, side: int = 512) -> np.ndarray:
    """Smooth content with real spatial correlation, unlike white noise."""
    rng = np.random.default_rng(seed)
    small = rng.normal(128, 40, (side // 16, side // 16))
    from PIL import Image
    up = Image.fromarray(np.clip(small, 0, 255).astype(np.uint8)).resize(
        (side, side), Image.BICUBIC)
    return np.clip(np.array(up, dtype=np.float64)
                   + rng.normal(0, 2, (side, side)), 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def standin(tmp_path_factory):
    root = tmp_path_factory.mktemp("ref")
    d = root / "BOSSbase_1.01"
    d.mkdir()
    for i in range(1, 13):
        (d / f"{i}.pgm").write_bytes(_pgm(_photographic(i, 128)))
    with zipfile.ZipFile(root / "BOSSbase_1.01.zip", "w") as zf:
        for i in range(1, 13):
            zf.write(d / f"{i}.pgm", f"BOSSbase_1.01/{i}.pgm")
    return root, d


# ---------------------------------------------------------------- pgm parsing

def test_reads_binary_pgm():
    arr = np.arange(64, dtype=np.uint8).reshape(8, 8)
    assert np.array_equal(read_pgm(_pgm(arr)), arr)


def test_matches_pillow():
    import io
    from PIL import Image
    arr = _photographic(7, 64)
    blob = _pgm(arr)
    assert np.array_equal(read_pgm(blob), np.array(Image.open(io.BytesIO(blob))))


def test_handles_comments_anywhere_in_the_header():
    arr = np.full((4, 4), 200, dtype=np.uint8)
    blob = b"P5\n# one\n4\n# two\n4\n255\n" + arr.tobytes()
    assert np.array_equal(read_pgm(blob), arr)


def test_handles_a_single_line_header():
    arr = np.full((4, 4), 33, dtype=np.uint8)
    assert np.array_equal(read_pgm(b"P5 4 4 255\n" + arr.tobytes()), arr)


def test_rejects_16_bit():
    with pytest.raises(CorpusError, match="16-bit"):
        read_pgm(b"P5\n4 4\n65535\n" + b"\x00" * 32)


def test_rejects_truncated():
    with pytest.raises(CorpusError, match="truncated"):
        read_pgm(b"P5\n512 512\n255\n" + b"\x00" * 100)


def test_rejects_wrong_magic():
    with pytest.raises(CorpusError, match="not a PGM"):
        read_pgm(b"\x89PNG\r\n\x1a\n")


# ------------------------------------------------------------------ discovery

def test_discovers_directory_and_zip(standin):
    root, d = standin
    for source in (d, root / "BOSSbase_1.01.zip"):
        corpus = discover(source)
        assert len(corpus) == 12
        assert corpus.read(corpus.members[0]).shape == (128, 128)


def test_numeric_ordering_not_lexicographic(standin):
    """1.pgm, 2.pgm, ... 10.pgm -- string sorting would put 10 before 2."""
    _root, d = standin
    corpus = discover(d)
    indices = [corpus.index_of(m) for m in corpus.members]
    assert indices == sorted(indices)


def test_sampling_is_deterministic(standin):
    _root, d = standin
    corpus = discover(d)
    a = corpus.sample(5, seed=3)
    b = corpus.sample(5, seed=3)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
    assert not all(np.array_equal(x, y)
                   for x, y in zip(a, corpus.sample(5, seed=4)))


def test_camera_partition_is_contiguous():
    ranges = sorted(BOSSBASE_CAMERAS_UNVERIFIED.values())
    assert ranges[0][0] == 1
    assert all(ranges[i][1] + 1 == ranges[i + 1][0] for i in range(len(ranges) - 1))
    assert sum(min(hi, 10_000) - lo + 1 for lo, hi in ranges if lo <= 10_000) == 10_000


def test_camera_members_filters_by_index(standin):
    _root, d = standin
    corpus = discover(d)
    assert len(corpus.camera_members("canon_eos_400d")) == 12
    assert corpus.camera_members("nikon_d70") == []
    with pytest.raises(CorpusError, match="unknown camera"):
        corpus.camera_members("nonexistent")


# --------------------------------------------------------------- verification

def test_verify_accepts_correlated_content(standin):
    _root, d = standin
    report = verify(discover(d), check=6)
    assert report["photographic"], report
    assert report["usable"]
    assert report["lag1_correlation"] > 0.80


def test_verify_rejects_white_noise(tmp_path):
    """The check that caught a stand-in built out of Gaussian noise.

    Noise loads cleanly and runs cleanly through both statistical gates,
    producing numbers that look like results. A corpus that loads is not a
    corpus that means anything.
    """
    rng = np.random.default_rng(0)
    for i in range(1, 7):
        arr = rng.integers(0, 256, (128, 128), dtype=np.uint8)
        (tmp_path / f"{i}.pgm").write_bytes(_pgm(arr))
    report = verify(discover(tmp_path), check=6)
    assert not report["photographic"]
    assert not report["usable"]
    assert any("not photographic" in p for p in report["problems"])


def test_find_bossbase_returns_none_when_absent(tmp_path):
    assert find_bossbase(tmp_path) is None


# ------------------------------------------ JPEG corpora (G-18 groundwork)

def test_discovers_a_jpeg_corpus(tmp_path):
    """ALASKA2 is JPEG; the loader used to find only PGM."""
    from PIL import Image
    rng = np.random.default_rng(3)
    for i in range(1, 7):
        low = rng.normal(128, 40, (32, 32))
        arr = np.array(Image.fromarray(np.clip(low, 0, 255).astype(np.uint8))
                       .resize((128, 128), Image.BICUBIC))
        Image.fromarray(arr).save(tmp_path / f"{i:05d}.jpg", quality=90)
    corpus_obj = discover(tmp_path, name="alaska2-like")
    assert len(corpus_obj) == 6
    assert corpus_obj.read(corpus_obj.members[0]).shape == (128, 128)
    report = verify(corpus_obj, check=4)
    assert report["photographic"] and report["usable"]


def test_undecodable_member_is_a_named_error():
    from steganalysis.reference import decode_image
    with pytest.raises(CorpusError, match="cannot decode"):
        decode_image("broken.jpg", b"not a jpeg at all")


# ------------------------------------ named processing chains (G-18)

def test_pipelines_preserve_shape_and_dtype():
    from steganalysis.reference import PIPELINES, apply_pipeline
    rng = np.random.default_rng(5)
    img = np.clip(rng.normal(128, 30, (96, 96)), 0, 255).astype(np.uint8)
    for name in PIPELINES:
        out = apply_pipeline([img], name)[0]
        assert out.shape == img.shape, name
        assert out.dtype == np.uint8, name


def test_pipelines_actually_change_the_noise_floor():
    """A 'second processing chain' that leaves the residual alone is not one."""
    from steganalysis.reference import apply_pipeline
    rng = np.random.default_rng(6)
    img = np.clip(rng.normal(128, 30, (96, 96)), 0, 255).astype(np.uint8)

    def high_freq(a):
        return float(np.mean(np.abs(np.diff(a.astype(float), axis=1))))

    base = high_freq(apply_pipeline([img], "native")[0])
    assert high_freq(apply_pipeline([img], "box_half")[0]) < base * 0.9
    assert high_freq(apply_pipeline([img], "sharpen")[0]) > base * 1.1


def test_unknown_pipeline_is_a_named_error():
    from steganalysis.reference import apply_pipeline
    with pytest.raises(CorpusError, match="unknown pipeline"):
        apply_pipeline([np.zeros((8, 8), dtype=np.uint8)], "nope")
