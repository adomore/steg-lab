"""From-scratch PNG structural parser.

Gate G1 requires that the structural view of a PNG be derived *without*
asking an image library to decode it.  Nothing in this module calls PIL,
OpenCV or any other decoder: it walks the byte stream and reports what is
physically there, including bytes that a decoder would silently ignore.

That distinction is the whole point.  A decoder answers "what picture is
this?"; a steganalyst needs "what bytes are in this file, and does every
one of them have a reason to exist?".
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import List, Optional

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Chunk types defined by the PNG specification (ISO/IEC 15948).  Anything
# outside this set is either a registered extension or a private chunk, and
# private chunks are a classic carrier.
SPEC_CHUNKS = {
    "IHDR", "PLTE", "IDAT", "IEND",
    "tRNS", "cHRM", "gAMA", "iCCP", "sBIT", "sRGB",
    "tEXt", "zTXt", "iTXt", "bKGD", "hIST", "pHYs",
    "sPLT", "tIME", "eXIf", "acTL", "fcTL", "fdAT",
    "cICP", "mDCv", "cLLi",
}

TEXT_CHUNKS = {"tEXt", "zTXt", "iTXt"}


@dataclass
class Chunk:
    """One physical PNG chunk: length | type | data | crc."""

    offset: int          # offset of the 4-byte length field
    length: int          # declared data length
    ctype: str           # 4-character type code
    data: bytes          # raw data bytes (as stored)
    crc_stored: int
    crc_computed: int
    truncated: bool = False

    @property
    def crc_ok(self) -> bool:
        return self.crc_stored == self.crc_computed

    @property
    def total_size(self) -> int:
        return 12 + self.length

    # PNG encodes four property bits in the *case* of the four type letters.
    # Getting these round the wrong way is a classic error -- the private
    # bit is the SECOND letter, not the third; the third is reserved and is
    # required to be uppercase.  Gate G1 exists partly to catch this.
    #
    #   letter 1 lowercase -> ancillary (a decoder may skip it)
    #   letter 2 lowercase -> private   (not in the registry)
    #   letter 3 uppercase -> reserved  (anything else is malformed)
    #   letter 4 lowercase -> safe to copy across unrelated edits

    @property
    def is_ancillary(self) -> bool:
        return self.ctype[0].islower()

    @property
    def is_private(self) -> bool:
        return self.ctype[1].islower()

    @property
    def reserved_bit_ok(self) -> bool:
        return self.ctype[2].isupper()

    @property
    def is_safe_to_copy(self) -> bool:
        return self.ctype[3].islower()

    @property
    def is_known(self) -> bool:
        return self.ctype in SPEC_CHUNKS


@dataclass
class Ihdr:
    width: int
    height: int
    bit_depth: int
    color_type: int
    compression: int
    filter_method: int
    interlace: int

    @property
    def channels(self) -> int:
        return {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(self.color_type, 1)

    @property
    def is_palette(self) -> bool:
        return self.color_type == 3

    def raw_scanline_bytes(self, width: Optional[int] = None) -> int:
        """Bytes per scanline before filtering, plus the filter byte."""
        w = self.width if width is None else width
        bits = w * self.channels * self.bit_depth
        return (bits + 7) // 8 + 1

    #: Adam7 pass geometry: (x_start, y_start, x_step, y_step).
    ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
             (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))

    def expected_raw_size(self, height: Optional[int] = None) -> int:
        """Size of the fully unfiltered pixel stream.

        Handles Adam7 as well as the flat case. An interlaced PNG is not one
        image stream but seven, each with its own dimensions and its own filter
        byte per row, so the flat formula undercounts it badly -- which is why
        the height-truncation check used to skip interlaced files entirely
        rather than report a surplus it could not interpret (gap G-7).
        """
        h = self.height if height is None else height
        if self.interlace == 0:
            return self.raw_scanline_bytes() * h

        total = 0
        for x0, y0, xs, ys in self.ADAM7:
            pw = (self.width - x0 + xs - 1) // xs if self.width > x0 else 0
            ph = (h - y0 + ys - 1) // ys if h > y0 else 0
            if pw > 0 and ph > 0:
                total += ph * self.raw_scanline_bytes(pw)
        return total

    def height_for_raw_size(self, raw_bytes: int, limit: int = 1 << 16
                            ) -> Optional[int]:
        """Smallest height whose unfiltered stream is exactly `raw_bytes`.

        For a flat image this is a division; for Adam7 it is not, because the
        seven passes gain rows at different heights. Searching upward from the
        declared height is exact and costs nothing at PNG scales.
        """
        if raw_bytes < 0:
            return None
        for h in range(self.height, min(limit, self.height + limit) + 1):
            size = self.expected_raw_size(h)
            if size == raw_bytes:
                return h
            if size > raw_bytes:
                return None
        return None


@dataclass
class PngFile:
    data: bytes
    chunks: List[Chunk] = field(default_factory=list)
    ihdr: Optional[Ihdr] = None
    iend_end: Optional[int] = None   # first byte AFTER the IEND chunk
    errors: List[str] = field(default_factory=list)

    @property
    def trailing(self) -> bytes:
        """Bytes physically present after the IEND chunk."""
        if self.iend_end is None:
            return b""
        return self.data[self.iend_end:]

    @property
    def trailing_offset(self) -> Optional[int]:
        return self.iend_end

    def chunks_of(self, ctype: str) -> List[Chunk]:
        return [c for c in self.chunks if c.ctype == ctype]

    def idat_payload(self) -> bytes:
        return b"".join(c.data for c in self.chunks_of("IDAT"))

    def bad_crc_chunks(self) -> List[Chunk]:
        # A truncated chunk has no stored CRC to compare against. Counting it
        # as a mismatch would upgrade "damaged in transit" into "edited after
        # writing" -- a much stronger claim, and one the bytes do not support.
        return [c for c in self.chunks if not c.crc_ok and not c.truncated]

    def unknown_chunks(self) -> List[Chunk]:
        return [c for c in self.chunks if not c.is_known]

    def summary(self) -> str:
        lines = []
        for c in self.chunks:
            flag = "" if c.crc_ok else "  <-- CRC MISMATCH"
            lines.append(f"{c.offset:>10}  {c.ctype}  len={c.length}{flag}")
        return "\n".join(lines)


def parse_png(data: bytes) -> PngFile:
    """Walk a PNG byte stream chunk by chunk.

    The parser is deliberately tolerant: a malformed file is a *finding*,
    not an exception.  Errors are collected instead of raised so the caller
    can reason about half-broken carriers.
    """
    png = PngFile(data=data)

    if not data.startswith(PNG_MAGIC):
        png.errors.append("missing PNG signature")
        return png

    pos = len(PNG_MAGIC)
    n = len(data)

    while pos + 8 <= n:
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype_raw = data[pos + 4:pos + 8]
        try:
            ctype = ctype_raw.decode("ascii")
        except UnicodeDecodeError:
            png.errors.append(f"non-ASCII chunk type at offset {pos}")
            break

        end_of_data = pos + 8 + length
        truncated = end_of_data + 4 > n
        chunk_data = data[pos + 8:min(end_of_data, n)]
        if truncated:
            png.errors.append(
                f"chunk {ctype} at {pos} declares {length} bytes but the file ends early"
            )
            crc_stored = -1
        else:
            (crc_stored,) = struct.unpack(">I", data[end_of_data:end_of_data + 4])

        crc_computed = zlib.crc32(ctype_raw + chunk_data) & 0xFFFFFFFF

        chunk = Chunk(
            offset=pos,
            length=length,
            ctype=ctype,
            data=chunk_data,
            crc_stored=crc_stored,
            crc_computed=crc_computed,
            truncated=truncated,
        )
        png.chunks.append(chunk)

        if ctype == "IHDR" and len(chunk_data) >= 13:
            w, h, bd, ct, comp, filt, inter = struct.unpack(">IIBBBBB", chunk_data[:13])
            png.ihdr = Ihdr(w, h, bd, ct, comp, filt, inter)

        if truncated:
            break

        pos = end_of_data + 4

        if ctype == "IEND":
            png.iend_end = pos
            break

    if png.iend_end is None and not png.errors:
        png.errors.append("no IEND chunk found")

    return png


def encode_adam7(pixels: "np.ndarray", declared_height: Optional[int] = None) -> bytes:
    """Build a genuinely interlaced PNG. Written because nothing else would.

    Pillow's PNG writer in this environment ignores an `interlace` argument, so
    a fixture for gap G-7 could not be produced with it -- and a test that
    silently exercises the non-interlaced path while claiming to test Adam7 is
    worse than no test. This lays out the seven passes itself, with filter type
    0 on every row, which is legal and keeps the encoder short.

    `declared_height` writes a different height into IHDR than the pixel data
    contains, which is the height-truncation carrier of lab 04.
    """
    import numpy as np
    import struct as _struct
    import zlib as _zlib

    arr = np.asarray(pixels, dtype=np.uint8)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    h, w, ch = arr.shape
    colour = {1: 0, 3: 2, 4: 6}[ch]

    raw = bytearray()
    for x0, y0, xs, ys in Ihdr.ADAM7:
        rows = range(y0, h, ys)
        cols = list(range(x0, w, xs))
        if not cols:
            continue
        for y in rows:
            raw.append(0)                     # filter type None
            raw.extend(arr[y, cols].tobytes())

    def chunk(ctype: bytes, body: bytes) -> bytes:
        return (_struct.pack(">I", len(body)) + ctype + body
                + _struct.pack(">I", _zlib.crc32(ctype + body) & 0xFFFFFFFF))

    ihdr = _struct.pack(">IIBBBBB", w,
                        h if declared_height is None else declared_height,
                        8, colour, 0, 0, 1)
    return (PNG_MAGIC + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", _zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


def decode_text_chunk(chunk: Chunk) -> tuple[str, str]:
    """Return (keyword, text) for tEXt / zTXt / iTXt chunks."""
    if chunk.ctype == "tEXt":
        kw, _, txt = chunk.data.partition(b"\x00")
        return kw.decode("latin-1"), txt.decode("latin-1", "replace")

    if chunk.ctype == "zTXt":
        kw, _, rest = chunk.data.partition(b"\x00")
        if not rest:
            return kw.decode("latin-1"), ""
        try:
            txt = zlib.decompress(rest[1:])
        except zlib.error:
            txt = rest[1:]
        return kw.decode("latin-1"), txt.decode("latin-1", "replace")

    if chunk.ctype == "iTXt":
        parts = chunk.data.split(b"\x00", 1)
        kw = parts[0].decode("utf-8", "replace")
        rest = parts[1] if len(parts) > 1 else b""
        if len(rest) < 2:
            return kw, ""
        compressed = rest[0] == 1
        body = rest[1:]
        # language tag, translated keyword, then the text
        segs = body.split(b"\x00", 3)
        txt = segs[-1] if segs else b""
        if compressed:
            try:
                txt = zlib.decompress(txt)
            except zlib.error:
                pass
        return kw, txt.decode("utf-8", "replace")

    return "", ""


def inflate_idat(png: PngFile) -> Optional[bytes]:
    """Inflate the concatenated IDAT stream, tolerating trailing garbage.

    Returns None when the stream cannot be inflated at all.  A *partial*
    inflate that leaves unused bytes is itself a signal, so callers should
    compare len(result) against ihdr.expected_raw_size().
    """
    payload = png.idat_payload()
    if not payload:
        return None
    obj = zlib.decompressobj()
    try:
        out = obj.decompress(payload)
        out += obj.flush()
    except zlib.error:
        return None
    return out
