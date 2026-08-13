"""Lab 22 -- video, where the carrier is redundant with itself.

A video is not one carrier. It is a sequence of carriers that are nearly
identical to each other, and that redundancy is a channel the analyst has and
the embedder does not.

**The temporal signal.** In a static region of a clean clip, consecutive frames
carry the same pixel values, so their least significant bits are the same bits.
Embedding randomises them. Measuring the per-pixel LSB flip rate between
consecutive frames therefore separates a static background that was left alone
(near 0) from one that was written into (near 0.5) -- and no single-image
detector can see this, because it needs two frames to exist.

It is the same shape of argument as lab 18's silent passage: find the part of
the carrier that should be exactly predictable, and check whether it is.

**And the limitation is the headline.** Every lossy codec rewrites pixels
between frames on its own. That destroys the payload and the signal together,
so this works on lossless video and nothing else -- measured below rather than
asserted. A report that says "no steganography found" in an H.264 file has said
much less than it appears to.

Domain    : video
Algorithm : frame-lsb / container-append
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.avi import AviFile, frames, parse_avi, render_avi
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "video"
DOMAIN = "video"
ALGORITHM = "frame-lsb"

#: A pixel whose value changes by at most this much between two frames is
#: treated as static. Not zero, because sensor noise moves real pixels by one
#: or two levels and a zero tolerance would find no static region in any clip
#: shot by a camera.
STATIC_TOLERANCE = 2

#: Peak per-pair flip rate above which the static region was written into.
#: Measured, not quoted: over 16 clean noise-free clips the peak never exceeded
#: 0.00814, so 0.02 clears the observed ceiling with about 2.5x of margin. A
#: 100-byte payload measures 0.0217 and a 400-byte one 0.0835. Re-measure it
#: for any other source -- like every threshold here it is a property of the
#: carrier.
FLIP_THRESHOLD = 0.02
CLEAN_PEAK_CEILING = 0.00814

#: A clip whose static region already flips this often carries no usable
#: signal: sensor noise has randomised the low bit before any embedder touched
#: it. The check declines rather than guessing, which is the same move the
#: pipeline makes when it refuses to apply a grayscale threshold to a colour
#: carrier -- declining to run is a result.
NOISE_FLOOR = 0.05


def embed(cover: bytes, payload: bytes, skip_frames: int = 1) -> bytes:
    """Sequential LSB replacement across frames, starting after `skip_frames`.

    Skipping the first frame is what a careful embedder does: the opening
    frame is the one a thumbnailer extracts, so leaving it alone keeps the
    preview pixel-identical to the original. It also means a detector that
    only looks at frame zero finds nothing.
    """
    video = frames(parse_avi(cover)).copy()
    if skip_frames >= len(video):
        raise ValueError("skip_frames covers the whole clip")

    flat = video[skip_frames:].reshape(-1)
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    if bits.size > flat.size:
        raise ValueError(f"payload needs {bits.size} samples, "
                         f"carrier has {flat.size}")
    flat[: bits.size] = (flat[: bits.size] & 0xFE) | bits
    video[skip_frames:] = flat.reshape(video[skip_frames:].shape)
    return render_avi(video)


def extract(data: bytes, nbytes: int, skip_frames: int = 1) -> bytes:
    video = frames(parse_avi(data))
    flat = video[skip_frames:].reshape(-1)
    bits = (flat[: nbytes * 8] & 1).astype(np.uint8)
    return np.packbits(bits).tobytes()


def append_payload(cover: bytes, payload: bytes) -> bytes:
    """The container channel: bytes past the RIFF size. Same as lab 01."""
    avi = parse_avi(cover)
    return avi.data[:avi.riff_end] + payload


def temporal_profile(data: bytes) -> Optional[Dict[str, float]]:
    """LSB flip rate between consecutive frames, inside the static region.

    The static mask is computed from the pixel VALUES, which embedding barely
    moves -- an LSB flip changes a value by one, well inside the tolerance. So
    the mask a detector derives from a stego clip is essentially the mask it
    would derive from the cover, and the measurement is not circular.
    """
    try:
        video = frames(parse_avi(data)).astype(np.int16)
    except Exception:
        return None
    if len(video) < 3:
        return None

    static_rates = []
    static_fractions = []
    for a, b in zip(video[:-1], video[1:]):
        static = np.abs(a - b) <= STATIC_TOLERANCE
        static_fractions.append(float(static.mean()))
        if static.sum() >= 64:
            flips = (a & 1) != (b & 1)
            static_rates.append(float(flips[static].mean()))

    if not static_rates:
        return None
    rates = np.array(static_rates)

    # PER PAIR, not averaged over the clip. A payload occupies a prefix of the
    # embedding order, so it lands in the first frames and the pairs after it
    # are untouched. Averaging over the whole clip divides the signal by the
    # frame count and hides it -- measured, a 400-byte payload gave 0.0076 as a
    # clip mean and 0.18 in the pair it actually occupied. Same lesson as lab
    # 13's windowed chi-square and lab 10's.
    return {"frame_pairs": int(rates.size),
            "static_fraction": float(np.mean(static_fractions)),
            "static_lsb_flip_rate": float(rates.mean()),
            "peak_pair_flip_rate": float(rates.max()),
            "peak_pair_index": int(rates.argmax()),
            "median_pair_flip_rate": float(np.median(rates))}


def detect(data: bytes, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None,
           payload_bytes: int = 0) -> Report:
    report = Report(carrier=name)
    avi = parse_avi(data)

    # Container first, because it is deterministic and yields the payload.
    if avi.trailing:
        level = cap_without_baseline(Evidence.E4, baseline)
        report.add(Finding(
            carrier=name, level=level, detector="video_trailing_data",
            claim=(f"{len(avi.trailing)} bytes follow the size the RIFF header "
                   f"declares"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="container-append" if level >= Evidence.E3 else None,
            payload=avi.trailing if level >= Evidence.E4 else None,
            payload_offset=avi.riff_end,
            baseline=baseline,
        ))

    profile = temporal_profile(data)

    # Applicability before verdict. If the clip's own noise already randomises
    # the low bit, this check cannot distinguish anything and says so instead
    # of producing a number.
    if profile and profile["median_pair_flip_rate"] >= NOISE_FLOOR:
        report.add(Finding(
            carrier=name, level=Evidence.E1, detector="video_temporal_lsb",
            claim=(f"the static region's low bit already flips at "
                   f"{profile['median_pair_flip_rate']:.1%} between frames, so "
                   f"sensor noise has randomised it and this check has no "
                   f"power on this carrier"),
            detail={k: round(v, 4) for k, v in profile.items()},
        ))
        return report

    if profile and profile["peak_pair_flip_rate"] >= FLIP_THRESHOLD:
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = (extract(data, payload_bytes) if payload_bytes
                   and level >= Evidence.E3 else None)
        if payload:
            level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="video_temporal_lsb",
            claim=(f"between frames {profile['peak_pair_index']} and "
                   f"{profile['peak_pair_index'] + 1}, least significant bits "
                   f"flip at {profile['peak_pair_flip_rate']:.1%} inside the "
                   f"static region against a clip median of "
                   f"{profile['median_pair_flip_rate']:.2%}; unchanged pixels "
                   f"carry unchanged bits"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm=ALGORITHM if level >= Evidence.E3 else None,
            payload=payload,
            baseline=baseline,
            detail={k: round(v, 4) for k, v in profile.items()},
        ))
    return report


def build_sample(cover: bytes, payload: bytes) -> bytes:
    return embed(cover, payload)
