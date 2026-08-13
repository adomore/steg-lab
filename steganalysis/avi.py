"""Uncompressed AVI, and seeded video with something that holds still.

AVI is RIFF, so the container walk is the same discipline as
`steganalysis.wav` and the byte accounting is the same as lab 01's. What is
new is the axis: a video is not one carrier, it is a sequence of carriers that
are *nearly identical to each other*, and that redundancy is the whole of lab
22.

Frames are written uncompressed (`DIB ` / BI_RGB) for one reason. Every lossy
codec rewrites pixel values between frames on its own, which destroys both the
payload and the signal used to find it. A lab built on compressed video would
be measuring the codec. Building it on uncompressed video makes the limitation
explicit instead, and the limitation is the honest headline: this detector
works on lossless video and nothing else.

Generated clips deliberately contain a static background and a moving object.
The static region is where inter-frame redundancy is highest and where LSB
embedding becomes structurally obvious -- the video analogue of the silent
passage in lab 18.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


class AviError(Exception):
    pass


@dataclass
class AviChunk:
    offset: int
    cid: str
    size: int
    data_offset: int

    @property
    def total_size(self) -> int:
        return 8 + self.size + (self.size & 1)


@dataclass
class AviFile:
    data: bytes
    chunks: List[AviChunk] = field(default_factory=list)
    width: int = 0
    height: int = 0
    frame_count: int = 0
    declared_size: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def riff_end(self) -> int:
        return 8 + self.declared_size

    @property
    def trailing(self) -> bytes:
        return self.data[self.riff_end:] if self.riff_end <= len(self.data) else b""

    def chunks_of(self, cid: str) -> List[AviChunk]:
        return [c for c in self.chunks if c.cid == cid]


def _walk(data: bytes, start: int, end: int, out: List[AviChunk]) -> None:
    """Recurse through RIFF/LIST containers collecting leaf chunks."""
    pos = start
    while pos + 8 <= end:
        cid = data[pos:pos + 4].decode("latin-1", "replace")
        (size,) = struct.unpack("<I", data[pos + 4:pos + 8])
        if cid in ("LIST", "RIFF"):
            out.append(AviChunk(pos, cid, size, pos + 12))
            _walk(data, pos + 12, min(pos + 8 + size, end), out)
        else:
            out.append(AviChunk(pos, cid, size, pos + 8))
        pos += 8 + size + (size & 1)


def parse_avi(data: bytes) -> AviFile:
    """Walk an AVI. Malformed input yields errors, not exceptions."""
    avi = AviFile(data=data)
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"AVI ":
        avi.errors.append("not a RIFF/AVI file")
        return avi

    (avi.declared_size,) = struct.unpack("<I", data[4:8])
    _walk(data, 12, min(avi.riff_end, len(data)), avi.chunks)

    for chunk in avi.chunks:
        if chunk.cid == "avih" and chunk.size >= 40:
            body = data[chunk.data_offset:chunk.data_offset + 40]
            avi.frame_count = struct.unpack("<I", body[16:20])[0]
            avi.width, avi.height = struct.unpack("<II", body[32:40])
    if not avi.chunks_of("avih"):
        avi.errors.append("no avih header")
    return avi


def frames(avi: AviFile) -> np.ndarray:
    """Return frames as (n, height, width, 3), top-down RGB.

    BI_RGB stores rows bottom-up and channels as BGR. Getting either wrong
    produces an array that looks like video and is mirrored or colour-swapped,
    which would quietly corrupt every per-pixel statistic downstream.
    """
    payload = [c for c in avi.chunks if c.cid.endswith("db") or c.cid.endswith("dc")]
    if not payload:
        raise AviError("no video data chunks")
    out = []
    stride = ((avi.width * 3 + 3) // 4) * 4
    for chunk in payload:
        raw = avi.data[chunk.data_offset:chunk.data_offset + chunk.size]
        if len(raw) < stride * avi.height:
            continue
        rows = np.frombuffer(raw[:stride * avi.height],
                             dtype=np.uint8).reshape(avi.height, stride)
        pixels = rows[:, :avi.width * 3].reshape(avi.height, avi.width, 3)
        out.append(pixels[::-1, :, ::-1])          # bottom-up BGR -> top-down RGB
    return np.array(out)


def render_avi(video: np.ndarray, fps: int = 15) -> bytes:
    """Write frames as an uncompressed AVI with an index."""
    video = np.asarray(video, dtype=np.uint8)
    n, height, width, _ = video.shape
    stride = ((width * 3 + 3) // 4) * 4
    pad = stride - width * 3

    payloads = []
    for frame in video:
        rows = frame[::-1, :, ::-1].reshape(height, width * 3)
        if pad:
            rows = np.hstack([rows, np.zeros((height, pad), dtype=np.uint8)])
        payloads.append(rows.tobytes())

    frame_size = len(payloads[0])
    avih = struct.pack("<IIIIIIIIIIIIIIII", int(1e6 // fps), 0, 0, 0x10, n, 0,
                       1, frame_size, width, height, 0, 0, 0, 0, 0, 0)
    strh = (b"vids" + b"DIB " + struct.pack("<IHHIIIIIIIIi", 0, 0, 0, 0, 1, fps,
                                            0, n, frame_size, 0, 0, -1)
            + struct.pack("<hhhh", 0, 0, width, height))
    strf = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                       frame_size, 0, 0, 0, 0)

    def chunk(cid: bytes, body: bytes) -> bytes:
        return cid + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) & 1 else b"")

    strl = b"LIST" + struct.pack("<I", 4 + len(chunk(b"strh", strh))
                                 + len(chunk(b"strf", strf))) + b"strl"
    strl += chunk(b"strh", strh) + chunk(b"strf", strf)
    hdrl_body = b"hdrl" + chunk(b"avih", avih) + strl
    hdrl = b"LIST" + struct.pack("<I", len(hdrl_body)) + hdrl_body

    movi_body = b"movi" + b"".join(chunk(b"00db", p) for p in payloads)
    movi = b"LIST" + struct.pack("<I", len(movi_body)) + movi_body

    index = b""
    offset = 4
    for payload in payloads:
        index += b"00db" + struct.pack("<III", 0x10, offset, len(payload))
        offset += 8 + len(payload) + (len(payload) & 1)
    idx1 = chunk(b"idx1", index)

    body = b"AVI " + hdrl + movi + idx1
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --------------------------------------------------------------------------
# Seeded video
# --------------------------------------------------------------------------

@dataclass
class VideoSpec:
    name: str
    seed: int
    frames: int = 24
    width: int = 96
    height: int = 72
    #: Fraction of the frame the moving object occupies. The rest is static
    #: background, which is where inter-frame redundancy lives.
    motion_fraction: float = 0.15
    #: Sensor noise amplitude. Zero means consecutive static pixels are
    #: bit-identical, which is the easiest case; real cameras are noisier and
    #: the corpus covers both.
    noise: float = 0.0


def render_video(spec: VideoSpec) -> bytes:
    rng = np.random.default_rng(spec.seed)
    h, w = spec.height, spec.width

    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    background = np.stack([
        120 + 40 * np.sin(xs / 11.0) + 20 * np.cos(ys / 7.0),
        110 + 30 * np.cos(xs / 9.0),
        130 + 25 * np.sin(ys / 13.0),
    ], axis=-1)
    background = np.clip(background, 0, 255)

    radius = max(int(np.sqrt(spec.motion_fraction * h * w / np.pi)), 3)
    out = []
    for i in range(spec.frames):
        frame = background.copy()
        cx = radius + (i * 5) % max(w - 2 * radius, 1)
        cy = h // 2 + int(8 * np.sin(i / 3.0))
        mask = ((xs - cx) ** 2 + (ys - cy) ** 2) < radius ** 2
        frame[mask] = [230.0, 90.0, 60.0]
        if spec.noise:
            frame = frame + rng.normal(0, spec.noise, frame.shape)
        out.append(np.clip(frame, 0, 255).astype(np.uint8))
    return render_avi(np.array(out))


def default_video_specs(n: int = 12, seed0: int = 95_000) -> List[VideoSpec]:
    return [VideoSpec(name=f"clip_{i:03d}.avi", seed=seed0 + i,
                      frames=24, motion_fraction=[0.10, 0.15, 0.25][i % 3],
                      noise=[0.0, 0.0, 0.6][i % 3])
            for i in range(n)]
