"""F-group tests: audio carriers.

Two tests here encode format traps rather than results. Both are the kind that
fail silently: an 8-bit WAV whose silence sits at 128 rather than 0, and a
detector that looks for exact silence in a file where embedding is precisely
what stops it being exact.
"""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402
from steganalysis.wav import (AudioSpec, parse_wav, render_audio,  # noqa: E402
                              render_wav, samples)


def clip(seed: int, bits: int = 16, silence: float = 0.25) -> bytes:
    return render_audio(AudioSpec(f"c{seed}.wav", seed, bits=bits,
                                  silence_fraction=silence))


def payload(nbytes: int, seed: int) -> bytes:
    return np.random.default_rng(seed).integers(
        0, 256, nbytes, dtype=np.uint8).tobytes()


# ------------------------------------------------------------------ parser

def test_parser_agrees_with_the_stdlib_wave_module():
    """An independent implementation, the same discipline gate G1 applies."""
    for i in range(4):
        blob = clip(9_700_000 + i)
        mine = parse_wav(blob)
        got = samples(mine)
        with wave.open(io.BytesIO(blob)) as ref:
            assert mine.channels == ref.getnchannels()
            assert mine.sample_rate == ref.getframerate()
            assert got.shape[0] == ref.getnframes()
            raw = ref.readframes(ref.getnframes())
        assert np.array_equal(got, np.frombuffer(raw, dtype="<i2").reshape(-1, 1))


def test_byte_accounting_closes_on_a_clean_file():
    wav = parse_wav(clip(9_701_001))
    accounted, gaps = wav.accounted_bytes()
    assert wav.errors == []
    assert gaps == []
    assert accounted == wav.riff_end == len(wav.data)


def test_trailing_data_after_the_riff_size_is_visible():
    blob = clip(9_701_002) + b"APPENDED-PAYLOAD" * 4
    wav = parse_wav(blob)
    assert wav.trailing == b"APPENDED-PAYLOAD" * 4


def test_eight_bit_is_unsigned_and_wider_is_signed():
    """Getting this backwards yields a plausible array off by half scale."""
    assert samples(parse_wav(clip(9_702_001, bits=8))).dtype == np.uint8
    assert samples(parse_wav(clip(9_702_002, bits=16))).dtype == np.int16


# ------------------------------------------------------------------ lab 18

def test_silence_level_follows_the_sample_encoding():
    lab = load_lab("18_audio_lsb")
    assert lab.silence_level(np.dtype(np.uint8)) == 128
    assert lab.silence_level(np.dtype(np.int16)) == 0


def test_payload_round_trips_at_both_bit_depths():
    lab = load_lab("18_audio_lsb")
    data = payload(600, 21)
    for bits in (8, 16):
        stego = lab.embed(clip(9_703_000 + bits, bits=bits), data)
        assert lab.extract(stego, len(data)) == data, bits


def test_embedding_never_moves_a_sample_by_more_than_one():
    lab = load_lab("18_audio_lsb")
    cover = clip(9_704_001)
    stego = lab.embed(cover, payload(600, 22))
    a = samples(parse_wav(cover)).astype(np.int64)
    b = samples(parse_wav(stego)).astype(np.int64)
    assert np.all(np.abs(a - b) <= 1)


def test_bit_depth_defeats_the_statistical_detector():
    """The lab's central claim, asserted as a ratio.

    The estimator is identical; only the carrier's precision changes.
    """
    lab = load_lab("18_audio_lsb")
    data = payload(1200, 23)
    ratios = {}
    for bits in (8, 16):
        covers = [clip(9_705_000 + bits * 100 + i, bits=bits) for i in range(8)]
        clean = np.mean([lab.audio_weighted_stego(c) for c in covers])
        stego = np.mean([lab.audio_weighted_stego(lab.embed(c, data))
                         for c in covers])
        ratios[bits] = stego / max(clean, 1e-12)
    assert ratios[8] > 5.0, ratios
    assert ratios[16] < 2.0, ratios


def test_silence_check_is_one_sided_and_quiet_on_clean():
    lab = load_lab("18_audio_lsb")
    for bits in (8, 16):
        covers = [clip(9_706_000 + bits * 100 + i, bits=bits,
                       silence=[0.15, 0.25, 0.4][i % 3]) for i in range(9)]
        alarms = sum(1 for c in covers
                     if lab.detect(c, "c", baseline=None).verdict >= Evidence.E1)
        assert alarms == 0, f"{alarms}/9 false alarms at {bits}-bit"


def test_silence_check_needs_the_payload_to_reach_the_silence():
    """A miss with a stated cause is a result; a miss without one is a bug."""
    lab = load_lab("18_audio_lsb")
    cover = clip(9_707_001, silence=0.4)
    small = lab.detect(lab.embed(cover, payload(150, 24)), "s", baseline=None)
    large = lab.detect(lab.embed(cover, payload(2000, 25)), "s", baseline=None)
    assert small.verdict == Evidence.E0
    assert large.verdict >= Evidence.E1


def test_silence_free_carriers_are_invisible_to_the_structural_check():
    lab = load_lab("18_audio_lsb")
    for i in range(5):
        stego = lab.embed(clip(9_708_000 + i, silence=0.0), payload(1200, 26))
        assert lab.detect(stego, "s", baseline=None).verdict == Evidence.E0


def test_reaches_e4_with_a_baseline():
    lab = load_lab("18_audio_lsb")
    data = payload(2000, 27)
    stego = lab.embed(clip(9_709_001, silence=0.4), data)
    baseline = FalsePositiveBaseline("audio_silence_lsb", 16, 0, 0.02,
                                     "16 same-source clean clips")
    report = lab.detect(stego, "s", baseline=baseline, payload_bytes=len(data))
    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == data


def test_capacity_is_enforced():
    lab = load_lab("18_audio_lsb")
    with pytest.raises(ValueError, match="payload needs"):
        lab.embed(clip(9_710_001), payload(100_000, 28))
