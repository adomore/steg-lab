"""I-group tests: video carriers.

The parser test compares against ffmpeg's own decoder pixel-for-pixel when it
is installed, and skips cleanly when it is not.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis.avi import (VideoSpec, frames, parse_avi,  # noqa: E402
                              render_avi, render_video)
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402


def clip(seed: int, noise: float = 0.0, n: int = 24) -> bytes:
    return render_video(VideoSpec(f"c{seed}.avi", seed, frames=n, noise=noise))


def payload(nbytes: int, seed: int) -> bytes:
    return np.random.default_rng(seed).integers(
        0, 256, nbytes, dtype=np.uint8).tobytes()


def baseline() -> FalsePositiveBaseline:
    return FalsePositiveBaseline("video_temporal_lsb", 8, 0, 0.02,
                                 "8 noise-free same-source clips")


# ------------------------------------------------------------------ parser

def test_parser_reads_its_own_output():
    avi = parse_avi(clip(97_001))
    assert avi.errors == []
    assert (avi.width, avi.height, avi.frame_count) == (96, 72, 24)
    assert frames(avi).shape == (24, 72, 96, 3)


def test_byte_accounting_closes():
    avi = parse_avi(clip(97_002))
    assert avi.riff_end == len(avi.data)
    assert avi.trailing == b""


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_frames_match_ffmpegs_decoder_pixel_for_pixel():
    """BI_RGB is bottom-up BGR; getting it wrong yields plausible wrong pixels."""
    blob = clip(97_003, n=8)
    mine = frames(parse_avi(blob))
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "c.avi"
        path.write_bytes(blob)
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True)
        assert out.returncode == 0, out.stderr[:200]
    ref = np.frombuffer(out.stdout, dtype=np.uint8).reshape(mine.shape)
    assert np.array_equal(ref, mine)


# ------------------------------------------------------------------ lab 22

def test_payload_round_trips():
    lab = load_lab("22_video")
    data = payload(400, 41)
    stego = lab.embed(clip(97_010), data)
    assert lab.extract(stego, len(data)) == data


def test_first_frame_is_left_untouched():
    """A thumbnailer extracts frame zero; a careful embedder leaves it alone."""
    lab = load_lab("22_video")
    cover = clip(97_011)
    stego = lab.embed(cover, payload(400, 42))
    assert np.array_equal(frames(parse_avi(cover))[0], frames(parse_avi(stego))[0])


def test_temporal_signal_is_per_pair_not_per_clip():
    """Averaging over the clip divides the signal by the frame count."""
    lab = load_lab("22_video")
    stego = lab.embed(clip(97_012), payload(400, 43))
    profile = lab.temporal_profile(stego)
    assert profile["peak_pair_flip_rate"] > 10 * profile["static_lsb_flip_rate"]


def test_detects_and_stays_quiet_on_clean():
    lab = load_lab("22_video")
    base = baseline()
    clips = [clip(97_020 + i) for i in range(6)]
    alarms = sum(1 for c in clips
                 if lab.detect(c, "c", baseline=base).verdict >= Evidence.E3)
    assert alarms == 0, f"{alarms}/6 false positives"
    found = sum(1 for i, c in enumerate(clips)
                if lab.detect(lab.embed(c, payload(400, 50 + i)), "s",
                              baseline=base).verdict >= Evidence.E3)
    assert found == 6, f"detected {found}/6"


def test_sensor_noise_makes_the_check_decline():
    """The applicability check: no power, so no verdict."""
    lab = load_lab("22_video")
    noisy = clip(97_030, noise=0.6)
    assert lab.temporal_profile(noisy)["median_pair_flip_rate"] > 0.4
    report = lab.detect(noisy, "n", baseline=baseline())
    assert report.verdict == Evidence.E1
    assert "no power" in report.findings[0].claim


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_lossy_re_encoding_destroys_payload_and_signal_together():
    """The headline limitation, asserted rather than described."""
    lab = load_lab("22_video")
    data = payload(400, 44)
    stego = lab.embed(clip(97_040), data)
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "s.avi", Path(td) / "o.avi"
        src.write_bytes(stego)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                        "-c:v", "mpeg4", "-q:v", "3", str(dst)], check=True)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(dst),
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
    video = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 72, 96, 3)
    lossy = render_avi(video)
    assert lab.extract(lossy, len(data)) != data
    assert lab.detect(lossy, "l", baseline=baseline()).verdict == Evidence.E1


def test_container_append_reaches_e4():
    lab = load_lab("22_video")
    data = b"APPENDED" * 8
    stego = lab.append_payload(clip(97_050), data)
    report = lab.detect(stego, "a", baseline=baseline())
    assert report.verdict == Evidence.E4
    assert any(f.payload == data for f in report.findings)


def test_capacity_is_enforced():
    lab = load_lab("22_video")
    with pytest.raises(ValueError, match="payload needs"):
        lab.embed(clip(97_060, n=4), payload(200_000, 45))
