"""Baseline JPEG entropy encoder -- writing modified coefficients back out.

`steganalysis.jpeg.decode_scan` has been able to recover DCT coefficients
since P0. Putting changed coefficients *back* into a valid JPEG is a
different problem, and until now it was gap G-14: T2 could measure F5 and
Jsteg on coefficient arrays, but no C-group lab could produce an actual
stego JPEG to detect.

The design decision that matters here is Huffman tables. Reusing the source
file's tables is tempting and wrong: changing a coefficient can change its
magnitude category, producing a (run, size) symbol the original table never
contained, and the encode then fails on exactly the inputs we care about --
the ones the embedder touched. So tables are rebuilt from the symbols
actually present, using the code-size procedure from JPEG Annex K.2. That
also makes the output smaller, which is what `jpegtran -optimize` does.

Two deliberate simplifications, both recorded rather than hidden:

  * Restart intervals are dropped. The output carries no DRI segment and no
    RST markers, which is valid baseline JPEG. Preserving them would mean
    reproducing the source's restart cadence for no analytical gain.
  * Only baseline sequential (SOF0) is supported, matching the decoder.
    Progressive input is refused, never guessed at.
"""

from __future__ import annotations

import struct
from typing import Dict, List, Optional, Tuple

import numpy as np

from .jpeg import JpegFile, ScanDecode, decode_scan, parse_jpeg


class EncodeError(Exception):
    pass


# --------------------------------------------------------------------------
# Optimal Huffman table construction (JPEG Annex K.2)
# --------------------------------------------------------------------------

def _code_sizes(freq: List[int]) -> List[int]:
    """Annex K.2 figure K.1: derive a code length for every used symbol.

    The reserved symbol at index 256 is given frequency 1 and never emitted.
    Its purpose is to guarantee that no real symbol ends up with the all-ones
    code, which JPEG forbids because decoders use it as a sentinel.
    """
    freq = list(freq) + [1]
    codesize = [0] * 257
    others = [-1] * 257

    while True:
        v1 = v2 = -1
        least = second = None
        for i in range(257):
            if freq[i] == 0:
                continue
            if least is None or freq[i] < least or (freq[i] == least and i > v1):
                second, v2 = least, v1
                least, v1 = freq[i], i
            elif second is None or freq[i] < second or (freq[i] == second and i > v2):
                second, v2 = freq[i], i
        if v2 < 0:
            break

        freq[v1] += freq[v2]
        freq[v2] = 0

        codesize[v1] += 1
        while others[v1] >= 0:
            v1 = others[v1]
            codesize[v1] += 1
        others[v1] = v2

        codesize[v2] += 1
        while others[v2] >= 0:
            v2 = others[v2]
            codesize[v2] += 1

    return codesize


def _limit_to_16_bits(bits: List[int]) -> List[int]:
    """Annex K.2 figure K.3: fold codes longer than 16 bits back in."""
    i = 32
    while i > 16:
        while bits[i] > 0:
            j = i - 2
            while bits[j] == 0:
                j -= 1
            bits[i] -= 2
            bits[i - 1] += 1
            bits[j + 1] += 2
            bits[j] -= 1
        i -= 1
    while i > 0 and bits[i] == 0:
        i -= 1
    bits[i] -= 1          # remove the reserved symbol
    return bits


def build_huffman_table(freq: List[int]) -> Tuple[List[int], List[int]]:
    """Return (BITS[16], HUFFVAL) for the given symbol frequencies."""
    codesize = _code_sizes(freq)

    bits = [0] * 33
    for i in range(257):
        if codesize[i] > 0:
            bits[codesize[i]] += 1
    bits = _limit_to_16_bits(bits)

    huffval: List[int] = []
    for length in range(1, 17):
        for symbol in range(256):
            if codesize[symbol] == length:
                huffval.append(symbol)

    return bits[1:17], huffval


def _encode_table(bits: List[int], huffval: List[int]) -> Dict[int, Tuple[int, int]]:
    """Map symbol -> (code, bit length)."""
    table: Dict[int, Tuple[int, int]] = {}
    code = 0
    k = 0
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            table[huffval[k]] = (code, length)
            k += 1
            code += 1
        code <<= 1
    return table


# --------------------------------------------------------------------------
# Bit writer
# --------------------------------------------------------------------------

class _BitWriter:
    """MSB-first bit writer that applies JPEG byte stuffing as it goes."""

    __slots__ = ("out", "buf", "cnt")

    def __init__(self) -> None:
        self.out = bytearray()
        self.buf = 0
        self.cnt = 0

    def write(self, value: int, length: int) -> None:
        for i in range(length - 1, -1, -1):
            self.buf = (self.buf << 1) | ((value >> i) & 1)
            self.cnt += 1
            if self.cnt == 8:
                self._flush_byte(self.buf & 0xFF)
                self.buf = 0
                self.cnt = 0

    def _flush_byte(self, byte: int) -> None:
        self.out.append(byte)
        if byte == 0xFF:
            self.out.append(0x00)      # stuffing, per the scan syntax

    def finish(self) -> bytes:
        if self.cnt:
            # Pad the final partial byte with 1-bits. Zeros would be legal
            # for the bit count but could form a 0xFF00 pair that shifts the
            # decoder's view of where the scan ends.
            self.buf = (self.buf << (8 - self.cnt)) | ((1 << (8 - self.cnt)) - 1)
            self._flush_byte(self.buf & 0xFF)
            self.buf = 0
            self.cnt = 0
        return bytes(self.out)


def _magnitude_category(value: int) -> int:
    return int(abs(value)).bit_length()


def _amplitude_bits(value: int, size: int) -> int:
    return value if value > 0 else value + (1 << size) - 1


# --------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------

def _component_layout(jpg: JpegFile):
    sofs = [s for s in jpg.segments if s.name == "SOF0"]
    if not sofs:
        raise EncodeError("only baseline sequential (SOF0) input is supported")
    sof = sofs[0].data
    height, width = struct.unpack(">HH", sof[1:5])
    ncomp = sof[5]
    comps = []
    for i in range(ncomp):
        cid, hv, tq = sof[6 + i * 3], sof[7 + i * 3], sof[8 + i * 3]
        comps.append({"id": cid, "h": hv >> 4, "v": hv & 0x0F, "tq": tq})

    sos = jpg.segments_of("SOS")
    if not sos:
        raise EncodeError("no SOS segment in the source file")
    sd = sos[0].data
    mapping = {}
    for i in range(sd[0]):
        mapping[sd[1 + i * 2]] = (sd[2 + i * 2] >> 4, sd[2 + i * 2] & 0x0F)

    return width, height, comps, mapping


def _gather_symbols(comps, mapping, coefficients, mcux, mcuy):
    """First pass: count symbol frequencies so the tables can be optimal."""
    dc_freq = {t: [0] * 256 for t in range(4)}
    ac_freq = {t: [0] * 256 for t in range(4)}
    cursor = {c["id"]: 0 for c in comps}
    pred = {c["id"]: 0 for c in comps}
    plan = []

    for _ in range(mcux * mcuy):
        for comp in comps:
            td, ta = mapping.get(comp["id"], (0, 0))
            for _b in range(comp["h"] * comp["v"]):
                block = coefficients[comp["id"]][cursor[comp["id"]]]
                cursor[comp["id"]] += 1

                diff = int(block[0]) - pred[comp["id"]]
                pred[comp["id"]] = int(block[0])
                size = _magnitude_category(diff)
                dc_freq[td][size] += 1
                entry = [(td, size, _amplitude_bits(diff, size) if size else 0, True)]

                run = 0
                for k in range(1, 64):
                    value = int(block[k])
                    if value == 0:
                        run += 1
                        continue
                    while run > 15:
                        ac_freq[ta][0xF0] += 1
                        entry.append((ta, 0xF0, 0, False))
                        run -= 16
                    s = _magnitude_category(value)
                    symbol = (run << 4) | s
                    ac_freq[ta][symbol] += 1
                    entry.append((ta, symbol, _amplitude_bits(value, s), False))
                    run = 0
                if run > 0:
                    ac_freq[ta][0x00] += 1
                    entry.append((ta, 0x00, 0, False))
                plan.append(entry)

    return dc_freq, ac_freq, plan


def encode_baseline(jpg: JpegFile,
                    coefficients: Dict[int, np.ndarray],
                    keep_comments: bool = True) -> bytes:
    """Rebuild a valid baseline JPEG from modified DCT coefficients.

    `coefficients` must have the same block ordering decode_scan produced:
    MCU-raster order, with a component's h*v blocks consecutive within
    each MCU.
    """
    width, height, comps, mapping = _component_layout(jpg)
    hmax = max(c["h"] for c in comps)
    vmax = max(c["v"] for c in comps)
    mcux = (width + 8 * hmax - 1) // (8 * hmax)
    mcuy = (height + 8 * vmax - 1) // (8 * vmax)

    for comp in comps:
        expected = mcux * mcuy * comp["h"] * comp["v"]
        got = len(coefficients[comp["id"]])
        if got != expected:
            raise EncodeError(f"component {comp['id']}: expected {expected} "
                              f"blocks, got {got}")

    dc_freq, ac_freq, plan = _gather_symbols(comps, mapping, coefficients, mcux, mcuy)

    dc_tables, ac_tables = {}, {}
    for t in range(4):
        if any(dc_freq[t]):
            dc_tables[t] = build_huffman_table(dc_freq[t])
        if any(ac_freq[t]):
            ac_tables[t] = build_huffman_table(ac_freq[t])

    dc_enc = {t: _encode_table(*v) for t, v in dc_tables.items()}
    ac_enc = {t: _encode_table(*v) for t, v in ac_tables.items()}

    writer = _BitWriter()
    for entry in plan:
        for table_id, symbol, amplitude, is_dc in entry:
            enc = dc_enc[table_id] if is_dc else ac_enc[table_id]
            if symbol not in enc:
                raise EncodeError(f"symbol {symbol} missing from a rebuilt table")
            code, length = enc[symbol]
            writer.write(code, length)
            size = symbol if is_dc else (symbol & 0x0F)
            if size:
                writer.write(amplitude, size)
    scan_bytes = writer.finish()

    out = bytearray(b"\xff\xd8")

    def emit(marker: int, payload: bytes) -> None:
        out.extend(bytes([0xFF, marker]))
        out.extend(struct.pack(">H", len(payload) + 2))
        out.extend(payload)

    for seg in jpg.segments:
        if seg.name == "APP0" or (keep_comments and seg.name in ("COM", "APP1")):
            emit(seg.marker, seg.data)
    for seg in jpg.segments_of("DQT"):
        emit(0xDB, seg.data)
    emit(0xC0, [s for s in jpg.segments if s.name == "SOF0"][0].data)

    for tid, (bits, huffval) in sorted(dc_tables.items()):
        emit(0xC4, bytes([0x00 | tid]) + bytes(bits) + bytes(huffval))
    for tid, (bits, huffval) in sorted(ac_tables.items()):
        emit(0xC4, bytes([0x10 | tid]) + bytes(bits) + bytes(huffval))

    emit(0xDA, jpg.segments_of("SOS")[0].data)
    out.extend(scan_bytes)
    out.extend(b"\xff\xd9")
    return bytes(out)


def recode(data: bytes, transform=None, component: int = 1) -> bytes:
    """Decode, optionally transform one component's coefficients, re-encode.

    `transform` receives the (blocks, 64) array in zig-zag order and returns
    a modified array of the same shape. With no transform this is a pure
    round trip, which is how the encoder is verified: the coefficients
    recovered from the output must equal those that went in.
    """
    jpg = parse_jpeg(data)
    decoded: ScanDecode = decode_scan(jpg, collect_coefficients=True)
    if not decoded.supported:
        raise EncodeError(f"cannot decode source: {decoded.reason}")

    coeffs = {cid: arr.copy() for cid, arr in decoded.coefficients.items()}
    if transform is not None:
        coeffs[component] = np.asarray(transform(coeffs[component]), dtype=np.int32)
    return encode_baseline(jpg, coeffs)


def coefficients_of(data: bytes) -> Optional[Dict[int, np.ndarray]]:
    decoded = decode_scan(parse_jpeg(data), collect_coefficients=True)
    return decoded.coefficients if decoded.supported else None
