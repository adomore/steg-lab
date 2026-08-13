"""From-scratch RIFF/WAVE parsing, and seeded audio covers.

Same rule as the image parsers: nothing here asks a decoder what the file
contains. It walks the chunk stream and reports what is physically there,
including bytes no player would ever read.

RIFF is a simpler container than PNG or JPEG and it leaks in the same three
places, which is worth noticing because it means the A-group habits transfer
unchanged:

  * the RIFF header declares a size, and anything past it is unaccounted for;
  * chunks are `id | size | payload`, with a pad byte when the size is odd,
    and a chunk whose payload nobody reads is a place to put things;
  * the `data` chunk declares its own length, so a `data` chunk shorter than
    the bytes that follow it hides the remainder in plain sight.

Audio covers are generated from seeds like the image corpus, for the same
reason: no binaries in the repository, and "same source" stays a checkable
property. They deliberately contain silent passages, because silence is where
audio steganalysis gets its equivalent of lab 04's height truncation.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


class WavError(Exception):
    pass


@dataclass
class RiffChunk:
    offset: int          # offset of the 4-byte id
    cid: str
    size: int            # declared payload size
    data_offset: int

    @property
    def total_size(self) -> int:
        # RIFF pads odd-length payloads to an even boundary.
        return 8 + self.size + (self.size & 1)


@dataclass
class WavFile:
    data: bytes
    chunks: List[RiffChunk] = field(default_factory=list)
    channels: int = 0
    sample_rate: int = 0
    bits: int = 0
    format_tag: int = 0
    declared_size: int = 0
    errors: List[str] = field(default_factory=list)

    def chunk(self, cid: str) -> Optional[RiffChunk]:
        for c in self.chunks:
            if c.cid == cid:
                return c
        return None

    @property
    def riff_end(self) -> int:
        """First byte after what the RIFF header claims the file contains."""
        return 8 + self.declared_size

    @property
    def trailing(self) -> bytes:
        return self.data[self.riff_end:] if self.riff_end <= len(self.data) else b""

    def accounted_bytes(self) -> Tuple[int, List[Tuple[int, int]]]:
        """Return (bytes claimed by chunks, [(gap offset, length)])."""
        spans = [(c.offset, c.offset + c.total_size) for c in self.chunks]
        spans.sort()
        gaps: List[Tuple[int, int]] = []
        cursor = 12                       # 'RIFF' + size + 'WAVE'
        accounted = 12
        for start, end in spans:
            if start > cursor:
                gaps.append((cursor, start - cursor))
            accounted += max(0, end - max(start, cursor))
            cursor = max(cursor, end)
        limit = min(self.riff_end, len(self.data))
        if cursor < limit:
            gaps.append((cursor, limit - cursor))
        return accounted, gaps


def parse_wav(data: bytes) -> WavFile:
    """Walk a RIFF/WAVE file. Malformed input yields errors, not exceptions."""
    wav = WavFile(data=data)
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        wav.errors.append("not a RIFF/WAVE file")
        return wav

    (wav.declared_size,) = struct.unpack("<I", data[4:8])
    pos = 12
    n = len(data)
    while pos + 8 <= n:
        cid = data[pos:pos + 4].decode("latin-1")
        (size,) = struct.unpack("<I", data[pos + 4:pos + 8])
        chunk = RiffChunk(offset=pos, cid=cid, size=size, data_offset=pos + 8)
        wav.chunks.append(chunk)

        if cid == "fmt " and size >= 16:
            (wav.format_tag, wav.channels, wav.sample_rate,
             _byte_rate, _align, wav.bits) = struct.unpack(
                "<HHIIHH", data[pos + 8:pos + 24])

        if pos + chunk.total_size > n:
            wav.errors.append(
                f"chunk '{cid}' at {pos} declares {size} bytes but the file "
                f"ends early")
            break
        pos += chunk.total_size

    if wav.chunk("fmt ") is None:
        wav.errors.append("no fmt chunk")
    if wav.chunk("data") is None:
        wav.errors.append("no data chunk")
    return wav


def samples(wav: WavFile) -> np.ndarray:
    """Return the PCM samples as (frames, channels).

    8-bit WAV is unsigned, everything wider is signed little-endian. Getting
    that backwards produces an array that looks plausible and is wrong by a
    half-scale offset, which would quietly poison every statistic downstream.
    """
    chunk = wav.chunk("data")
    if chunk is None:
        raise WavError("no data chunk")
    if wav.format_tag != 1:
        raise WavError(f"only PCM (format tag 1) is supported, found "
                       f"{wav.format_tag}")

    raw = wav.data[chunk.data_offset:chunk.data_offset + chunk.size]
    dtype = {8: np.uint8, 16: "<i2", 24: None, 32: "<i4"}.get(wav.bits)
    if dtype is None:
        raise WavError(f"{wav.bits}-bit PCM is not supported")

    arr = np.frombuffer(raw, dtype=dtype)
    usable = (arr.size // max(wav.channels, 1)) * max(wav.channels, 1)
    return arr[:usable].reshape(-1, max(wav.channels, 1))


def render_wav(frames: np.ndarray, sample_rate: int = 22050,
               bits: int = 16) -> bytes:
    """Write PCM samples as a minimal, valid WAVE file."""
    arr = np.asarray(frames)
    if arr.ndim == 1:
        arr = arr[:, None]
    channels = arr.shape[1]
    dtype = {8: np.uint8, 16: "<i2", 32: "<i4"}[bits]
    payload = arr.astype(dtype).tobytes()

    block_align = channels * bits // 8
    fmt = struct.pack("<HHIIHH", 1, channels, sample_rate,
                      sample_rate * block_align, block_align, bits)
    body = (b"WAVE"
            + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(payload)) + payload
            + (b"\x00" if len(payload) & 1 else b""))
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --------------------------------------------------------------------------
# Seeded covers
# --------------------------------------------------------------------------

@dataclass
class AudioSpec:
    name: str
    seed: int
    seconds: float = 1.0
    sample_rate: int = 22050
    bits: int = 16
    channels: int = 1
    #: Fraction of the clip that is digital silence. Real recordings have
    #: leaders, gaps and fades; silence is also where LSB embedding becomes
    #: structurally obvious, so a corpus without it would make the audio labs
    #: look easier than they are.
    silence_fraction: float = 0.25


def render_audio(spec: AudioSpec) -> bytes:
    """Deterministically render one audio cover to WAVE bytes."""
    rng = np.random.default_rng(spec.seed)
    n = int(spec.seconds * spec.sample_rate)
    t = np.arange(n) / spec.sample_rate

    signal = np.zeros(n)
    for _ in range(4):
        freq = float(rng.uniform(90, 2400))
        signal += rng.uniform(0.15, 1.0) * np.sin(2 * np.pi * freq * t
                                                  + rng.uniform(0, 2 * np.pi))
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.5, 3.0) * t)
    signal *= envelope
    signal += rng.normal(0, 0.02, n)

    silent = int(spec.silence_fraction * n)
    if silent:
        start = int(rng.integers(0, max(n - silent, 1)))
        signal[start:start + silent] = 0.0

    peak = np.max(np.abs(signal)) or 1.0
    if spec.bits == 8:
        pcm = np.clip(np.round(signal / peak * 100) + 128, 0, 255)
    else:
        limit = 2 ** (spec.bits - 1) - 1
        pcm = np.clip(np.round(signal / peak * limit * 0.8), -limit, limit)

    frames = np.repeat(pcm[:, None], spec.channels, axis=1)
    return render_wav(frames, spec.sample_rate, spec.bits)


def default_audio_specs(n: int = 24, bits: int = 16,
                        seed0: int = 70_000) -> List[AudioSpec]:
    return [AudioSpec(name=f"clip_{i:03d}.wav", seed=seed0 + i,
                      seconds=1.0, bits=bits,
                      silence_fraction=[0.0, 0.15, 0.25, 0.4][i % 4])
            for i in range(n)]
