"""Lab 18 -- audio LSB, where bit depth changes the answer and silence gives it away.

Audio looks like the spatial labs with one axis removed, and that reading is
wrong in a way worth measuring.

**Bit depth.** An 8-bit image sample spans 256 levels, so flipping its low bit
perturbs it by 1/256 of full scale. A 16-bit audio sample spans 65,536, so the
same flip perturbs it by 1/65,536 -- forty-eight decibels quieter relative to
the carrier. Every statistical detector that works on the residual is looking
for a signal two orders of magnitude smaller. Gate-style measurement below.

**Silence.** Audio has a structure images do not: passages of digital silence,
where every sample is exactly zero. LSB embedding turns those into a stream of
zeros and ones. Nothing about that is subtle, and no statistics are needed --
it is the audio equivalent of lab 04's height truncation, a carrier that is
perfectly valid and obviously wrong once you know where to look.

The pair makes the lab's point: raising the carrier's precision defeats the
statistical attack and does nothing at all about the structural one.

Domain    : audio
Algorithm : lsb-replacement
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)
from steganalysis.wav import parse_wav, render_wav, samples

NAME = "audio_lsb"
DOMAIN = "audio"
ALGORITHM = "lsb-replacement"

#: A run of at least this many consecutive near-silent samples is treated as a
#: silent passage. Short dips between waveform cycles are not silence.
SILENCE_RUN = 64


def silence_level(dtype: np.dtype) -> int:
    """The sample value that means silence, which is not always zero.

    8-bit WAV is UNSIGNED with midpoint 128; everything wider is signed with
    midpoint 0. Searching for zeros in an 8-bit clip finds the most negative
    excursions of the waveform and misses the silence entirely -- the same
    signed/unsigned trap `steganalysis.wav.samples` warns about, arriving from
    the other direction.
    """
    return 128 if np.dtype(dtype).kind == "u" else 0

#: Share of a silent run's samples allowed to be non-zero before the run is
#: called embedded. Digital silence is exactly zero; a clean encoder does not
#: sprinkle ones through it.
SILENCE_TOLERANCE = 0.02


def _flat(data: bytes) -> tuple:
    wav = parse_wav(data)
    frames = samples(wav)
    return wav, frames


def embed(cover: bytes, payload: bytes) -> bytes:
    """Sequential LSB replacement over PCM samples."""
    wav, frames = _flat(cover)
    flat = frames.reshape(-1).copy()
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    if bits.size > flat.size:
        raise ValueError(f"payload needs {bits.size} samples, "
                         f"carrier has {flat.size}")
    # ~1 is the Python int -2, which numpy refuses to cast into uint8. Taking
    # the mask through the array's own dtype gives 0xFE for unsigned and
    # 0xFFFE for signed, which is the same bit pattern either way.
    mask = flat.dtype.type(-2) if flat.dtype.kind == "i" else flat.dtype.type(0xFE)
    flat[: bits.size] = (flat[: bits.size] & mask) | bits.astype(flat.dtype)
    return render_wav(flat.reshape(frames.shape), wav.sample_rate, wav.bits)


def extract(data: bytes, nbytes: int) -> bytes:
    _wav, frames = _flat(data)
    bits = (frames.reshape(-1)[: nbytes * 8] & 1).astype(np.uint8)
    return np.packbits(bits).tobytes()


# --------------------------------------------------------------------------
# Structural: silence
# --------------------------------------------------------------------------

def silent_runs(track: np.ndarray, min_run: int = SILENCE_RUN) -> list:
    """Index ranges that look like digital silence, allowing for LSB noise.

    The search is for |sample| <= 1 rather than == 0 precisely because
    embedding is what puts the ones there. Looking for exact zeros would make
    an embedded silent passage invisible to the check meant to catch it.
    """
    centre = silence_level(track.dtype)
    quiet = np.abs(track.astype(np.int64) - centre) <= 1
    runs = []
    start = None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if i - start >= min_run:
                runs.append((start, i))
            start = None
    if start is not None and len(quiet) - start >= min_run:
        runs.append((start, len(quiet)))
    return runs


def silence_report(data: bytes) -> Optional[Dict[str, float]]:
    """How much of the silence is not silent."""
    try:
        _wav, frames = _flat(data)
    except Exception:
        return None
    track = frames[:, 0]
    runs = silent_runs(track)
    if not runs:
        return None

    centre = silence_level(track.dtype)
    total = sum(end - start for start, end in runs)
    nonzero = sum(int(np.count_nonzero(track[start:end] != centre))
                  for start, end in runs)
    ones = sum(int(np.count_nonzero(track[start:end] == centre + 1))
               for start, end in runs)
    # LSB replacement can only ever produce the silence level or one above it.
    # A genuinely quiet passage of a waveform crosses the level in BOTH
    # directions, so it also contains centre - 1. That asymmetry is what
    # separates "embedded silence" from "quiet music", and without it the
    # check produced false positives on 8-bit clips, where the quantiser makes
    # low-amplitude passages indistinguishable from silence by amplitude alone.
    below = sum(int(np.count_nonzero(track[start:end] == centre - 1))
                for start, end in runs)
    one_sided = (nonzero > 0 and below == 0)
    return {"silent_samples": total,
            "silence_level": centre,
            "nonzero_in_silence": nonzero,
            "ones_in_silence": ones,
            "below_level": below,
            "one_sided": one_sided,
            "fraction": nonzero / total if total else 0.0,
            "runs": len(runs)}


# --------------------------------------------------------------------------
# Statistical: weighted stego for one dimension
# --------------------------------------------------------------------------

def audio_weighted_stego(data: bytes) -> Optional[float]:
    """Weighted Stego with a two-neighbour predictor.

    The image version predicts a pixel from its four-neighbourhood. Audio has
    two neighbours, and the same estimator applies: does the residual between a
    sample and its predicted value correlate with the sample's parity?
    """
    try:
        _wav, frames = _flat(data)
    except Exception:
        return None
    track = frames[:, 0].astype(np.float64)
    if track.size < 8:
        return None

    predicted = np.empty_like(track)
    predicted[1:-1] = (track[:-2] + track[2:]) / 2.0
    predicted[0], predicted[-1] = track[1], track[-2]

    parity = 2.0 * (frames[:, 0].astype(np.int64) & 1) - 1.0
    local = np.abs(np.diff(track, prepend=track[0]))
    weights = 1.0 / (1.0 + local ** 2)
    weights /= weights.sum()
    return float(abs(2.0 * np.sum(weights * (track - predicted) * parity)))


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None,
           payload_bytes: int = 0) -> Report:
    report = Report(carrier=name)

    silence = silence_report(data)
    if (silence and silence["fraction"] > SILENCE_TOLERANCE
            and silence["one_sided"]):
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = None
        if payload_bytes and level >= Evidence.E3:
            payload = extract(data, payload_bytes)
            if payload:
                level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="audio_silence_lsb",
            claim=(f"{silence['nonzero_in_silence']} of "
                   f"{silence['silent_samples']} samples inside "
                   f"{silence['runs']} silent passage(s) are non-zero; digital "
                   f"silence is exactly zero"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm=ALGORITHM if level >= Evidence.E3 else None,
            payload=payload,
            baseline=baseline,
            detail={k: (round(v, 5) if isinstance(v, float) else v)
                    for k, v in silence.items()},
        ))
    return report


def build_sample(cover: bytes, payload: bytes) -> bytes:
    return embed(cover, payload)
