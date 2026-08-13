"""Container-level primitives shared by the A-group labs.

Signature scanning, entropy measurement, ZIP structure walking and the LSB
helpers that gate G0 needs.  Everything here is format-agnostic: it treats
a file as a byte string with declared boundaries and asks whether the bytes
inside those boundaries account for the file's length.
"""

from __future__ import annotations

import math
import struct
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

# Signatures worth finding *inside* another file.  A hit is not proof of
# anything -- compressed data contains arbitrary bytes -- but a hit that is
# also a structurally valid header of that type usually is.
SIGNATURES: Dict[str, bytes] = {
    "zip": b"PK\x03\x04",
    "zip_eocd": b"PK\x05\x06",
    "rar": b"Rar!\x1a\x07",
    "7z": b"7z\xbc\xaf\x27\x1c",
    "gzip": b"\x1f\x8b\x08",
    "pdf": b"%PDF-",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "gif87": b"GIF87a",
    "gif89": b"GIF89a",
    "elf": b"\x7fELF",
    "pe": b"MZ",
    "bzip2": b"BZh",
    "xz": b"\xfd7zXZ\x00",
    "sqlite": b"SQLite format 3\x00",
    "openssl_salted": b"Salted__",
}


def find_signatures(data: bytes, start: int = 0,
                    names: Optional[List[str]] = None) -> List[Tuple[int, str]]:
    """Return [(offset, signature_name)] for every embedded signature hit."""
    hits: List[Tuple[int, str]] = []
    wanted = SIGNATURES if names is None else {k: SIGNATURES[k] for k in names}
    for name, sig in wanted.items():
        pos = data.find(sig, start)
        while pos != -1:
            hits.append((pos, name))
            pos = data.find(sig, pos + 1)
    return sorted(hits)


def shannon_entropy(data: bytes) -> float:
    """Bits per byte.  ~8.0 means compressed or encrypted, ~4-5 means text."""
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    return printable / len(data)


def classify_blob(data: bytes) -> str:
    """A coarse label for an unexplained byte run."""
    if not data:
        return "empty"
    for name, sig in SIGNATURES.items():
        if data.startswith(sig):
            return f"{name}-header"
    ent = shannon_entropy(data)
    if printable_ratio(data) > 0.90:
        return "text"
    if ent > 7.5:
        return "compressed-or-encrypted"
    if ent < 2.0:
        return "low-entropy-padding"
    return "unknown-binary"


# --------------------------------------------------------------------------
# ZIP structure
# --------------------------------------------------------------------------

@dataclass
class ZipLocalEntry:
    offset: int
    version: int
    flags: int
    method: int
    crc32: int
    comp_size: int
    uncomp_size: int
    name: str
    extra: bytes
    data_offset: int

    @property
    def encrypted_flag(self) -> bool:
        return bool(self.flags & 0x0001)


@dataclass
class ZipCentralEntry:
    offset: int
    flags: int
    method: int
    comp_size: int
    uncomp_size: int
    name: str
    extra: bytes
    comment: bytes
    local_offset: int

    @property
    def encrypted_flag(self) -> bool:
        return bool(self.flags & 0x0001)


@dataclass
class ZipFileView:
    local: List[ZipLocalEntry]
    central: List[ZipCentralEntry]
    eocd_offset: Optional[int]
    archive_comment: bytes
    gaps: List[Tuple[int, int]]      # (offset, length) of unexplained runs


def parse_zip(data: bytes) -> ZipFileView:
    """Walk local headers, the central directory and the EOCD.

    Deliberately independent of the stdlib zipfile module: zipfile trusts
    the central directory and ignores everything the central directory does
    not mention, which is precisely where things get hidden.
    """
    local: List[ZipLocalEntry] = []
    pos = 0
    while True:
        pos = data.find(b"PK\x03\x04", pos)
        if pos == -1 or pos + 30 > len(data):
            break
        (ver, flags, method, _mt, _md, crc,
         csize, usize, nlen, elen) = struct.unpack("<HHHHHIIIHH", data[pos + 4:pos + 30])
        name = data[pos + 30:pos + 30 + nlen].decode("utf-8", "replace")
        extra = data[pos + 30 + nlen:pos + 30 + nlen + elen]
        dofs = pos + 30 + nlen + elen
        local.append(ZipLocalEntry(pos, ver, flags, method, crc,
                                   csize, usize, name, extra, dofs))
        pos = dofs + max(csize, 0)

    central: List[ZipCentralEntry] = []
    pos = 0
    while True:
        pos = data.find(b"PK\x01\x02", pos)
        if pos == -1 or pos + 46 > len(data):
            break
        (_vm, _vn, flags, method, _mt, _md, _crc, csize, usize,
         nlen, elen, clen, _dsk, _ia, _ea, lofs) = struct.unpack(
            "<HHHHHHIIIHHHHHII", data[pos + 4:pos + 46])
        name = data[pos + 46:pos + 46 + nlen].decode("utf-8", "replace")
        extra = data[pos + 46 + nlen:pos + 46 + nlen + elen]
        comment = data[pos + 46 + nlen + elen:pos + 46 + nlen + elen + clen]
        central.append(ZipCentralEntry(pos, flags, method, csize, usize,
                                       name, extra, comment, lofs))
        pos += 46 + nlen + elen + clen

    eocd = data.rfind(b"PK\x05\x06")
    comment = b""
    if eocd != -1 and eocd + 22 <= len(data):
        (clen,) = struct.unpack("<H", data[eocd + 20:eocd + 22])
        comment = data[eocd + 22:eocd + 22 + clen]

    gaps = _zip_gaps(data, local, central, eocd)
    return ZipFileView(local, central, eocd, comment, gaps)


def _zip_gaps(data: bytes, local: List[ZipLocalEntry],
              central: List[ZipCentralEntry], eocd: Optional[int]) -> List[Tuple[int, int]]:
    """Byte runs claimed by no ZIP structure."""
    covered: List[Tuple[int, int]] = []
    for e in local:
        covered.append((e.offset, e.data_offset + max(e.comp_size, 0)))
    for c in central:
        covered.append((c.offset, c.offset + 46 + len(c.name) + len(c.extra) + len(c.comment)))
    if eocd is not None and eocd != -1:
        covered.append((eocd, len(data)))
    covered.sort()

    gaps: List[Tuple[int, int]] = []
    cursor = 0
    for start, end in covered:
        if start > cursor:
            gaps.append((cursor, start - cursor))
        cursor = max(cursor, end)
    if cursor < len(data):
        gaps.append((cursor, len(data) - cursor))
    return [g for g in gaps if g[1] > 0]


# --------------------------------------------------------------------------
# LSB helpers (needed by gate G0's active-warden experiment)
# --------------------------------------------------------------------------

def bytes_to_bits(payload: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(payload, dtype=np.uint8))


def bits_to_bytes(bits: np.ndarray) -> bytes:
    usable = (len(bits) // 8) * 8
    return np.packbits(bits[:usable]).tobytes()


def lsb_replace(arr: np.ndarray, payload: bytes, seed: Optional[int] = None) -> np.ndarray:
    """Classic LSB replacement over a flattened pixel array.

    seed=None writes sequentially from offset 0 (the naive variant every
    CTF uses); an integer seed selects a pseudo-random permutation of
    positions, which is what real tools do and what defeats a purely
    sequential extractor.
    """
    flat = arr.reshape(-1).copy()
    bits = bytes_to_bits(payload)
    if len(bits) > flat.size:
        raise ValueError(f"payload needs {len(bits)} pixels, carrier has {flat.size}")
    if seed is None:
        idx = np.arange(len(bits))
    else:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(flat.size)[:len(bits)]
    flat[idx] = (flat[idx] & 0xFE) | bits.astype(np.uint8)
    return flat.reshape(arr.shape)


def lsb_extract(arr: np.ndarray, nbytes: int, seed: Optional[int] = None) -> bytes:
    flat = arr.reshape(-1)
    nbits = nbytes * 8
    if seed is None:
        idx = np.arange(min(nbits, flat.size))
    else:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(flat.size)[:nbits]
    return bits_to_bytes(flat[idx] & 1)


def bit_error_rate(a: bytes, b: bytes) -> float:
    """Fraction of differing bits over the overlapping prefix."""
    n = min(len(a), len(b))
    if n == 0:
        return float("nan")
    xa = np.unpackbits(np.frombuffer(a[:n], dtype=np.uint8))
    xb = np.unpackbits(np.frombuffer(b[:n], dtype=np.uint8))
    return float(np.mean(xa != xb))


def iter_runs(data: bytes, chunk: int = 4096) -> Iterator[Tuple[int, bytes]]:
    for off in range(0, len(data), chunk):
        yield off, data[off:off + chunk]
