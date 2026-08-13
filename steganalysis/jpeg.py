"""From-scratch JPEG structural parser.

Like steganalysis.png, this module never decodes an image.  It walks the
marker stream, isolates the entropy-coded segments, and reports every byte
that is not accounted for by the JPEG syntax.

Two structural facts do most of the work in the A-group labs:

  * The entropy-coded scan is byte-stuffed: a literal 0xFF inside the scan
    is stored as 0xFF 0x00.  Any other 0xFF xx pair terminates the scan.
    Walking that rule is what lets us find the *true* EOI rather than the
    first 0xFFD9-looking pair inside compressed data.
  * Everything after EOI is, by definition, not part of the image.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SOI = 0xD8
EOI = 0xD9

# Markers that stand alone (no length field follows).
STANDALONE = {0x01, SOI, EOI} | set(range(0xD0, 0xD8))  # TEM, SOI, EOI, RST0-7

MARKER_NAMES: Dict[int, str] = {
    0xC0: "SOF0", 0xC1: "SOF1", 0xC2: "SOF2", 0xC3: "SOF3",
    0xC4: "DHT", 0xC5: "SOF5", 0xC6: "SOF6", 0xC7: "SOF7",
    0xC8: "JPG", 0xC9: "SOF9", 0xCA: "SOF10", 0xCB: "SOF11",
    0xCC: "DAC", 0xCD: "SOF13", 0xCE: "SOF14", 0xCF: "SOF15",
    0xD8: "SOI", 0xD9: "EOI", 0xDA: "SOS", 0xDB: "DQT",
    0xDC: "DNL", 0xDD: "DRI", 0xDE: "DHP", 0xDF: "EXP",
    0xFE: "COM",
}
for _i in range(16):
    MARKER_NAMES[0xE0 + _i] = f"APP{_i}"
for _i in range(8):
    MARKER_NAMES[0xD0 + _i] = f"RST{_i}"

SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


@dataclass
class Segment:
    offset: int          # offset of the 0xFF byte
    marker: int          # second byte of the marker
    name: str
    length: int          # declared segment length (0 for standalone)
    data: bytes          # payload after the length field

    @property
    def total_size(self) -> int:
        return 2 if self.length == 0 else 2 + self.length


@dataclass
class ScanBlock:
    """One entropy-coded segment, i.e. the compressed bytes after an SOS."""

    start: int
    end: int
    stuffed_ff: int = 0
    restart_markers: int = 0

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass
class JpegFile:
    data: bytes
    segments: List[Segment] = field(default_factory=list)
    scans: List[ScanBlock] = field(default_factory=list)
    eoi_end: Optional[int] = None     # first byte AFTER 0xFFD9
    errors: List[str] = field(default_factory=list)

    @property
    def trailing(self) -> bytes:
        if self.eoi_end is None:
            return b""
        return self.data[self.eoi_end:]

    @property
    def trailing_offset(self) -> Optional[int]:
        return self.eoi_end

    def segments_of(self, name: str) -> List[Segment]:
        return [s for s in self.segments if s.name == name]

    def quant_tables(self) -> Dict[int, List[int]]:
        """Return {table_id: 64 coefficients in zig-zag order}."""
        tables: Dict[int, List[int]] = {}
        for seg in self.segments_of("DQT"):
            buf = seg.data
            i = 0
            while i < len(buf):
                pq, tq = buf[i] >> 4, buf[i] & 0x0F
                i += 1
                if pq == 0:
                    vals = list(buf[i:i + 64])
                    i += 64
                else:
                    vals = list(struct.unpack(">64H", buf[i:i + 128]))
                    i += 128
                tables[tq] = vals
        return tables

    def dimensions(self) -> Optional[tuple[int, int]]:
        for seg in self.segments:
            if seg.marker in SOF_MARKERS and len(seg.data) >= 5:
                h, w = struct.unpack(">HH", seg.data[1:5])
                return w, h
        return None

    def summary(self) -> str:
        lines = []
        for s in self.segments:
            lines.append(f"{s.offset:>10}  {s.name:<6} len={s.length}")
        for sc in self.scans:
            lines.append(f"{sc.start:>10}  <scan> {sc.size} bytes, "
                         f"{sc.stuffed_ff} stuffed FF, {sc.restart_markers} RST")
        return "\n".join(sorted(lines, key=lambda x: int(x.split()[0])))


def _scan_entropy(data: bytes, pos: int) -> ScanBlock:
    """Advance through an entropy-coded segment, honouring byte stuffing."""
    start = pos
    n = len(data)
    stuffed = 0
    restarts = 0
    while pos < n - 1:
        if data[pos] != 0xFF:
            pos += 1
            continue
        nxt = data[pos + 1]
        if nxt == 0x00:
            stuffed += 1
            pos += 2
            continue
        if 0xD0 <= nxt <= 0xD7:
            restarts += 1
            pos += 2
            continue
        if nxt == 0xFF:      # fill byte, stay in the scan
            pos += 1
            continue
        break
    return ScanBlock(start=start, end=pos, stuffed_ff=stuffed, restart_markers=restarts)


def parse_jpeg(data: bytes) -> JpegFile:
    """Walk a JPEG marker stream.  Malformed input yields errors, not raises."""
    jpg = JpegFile(data=data)
    n = len(data)

    if n < 2 or data[0] != 0xFF or data[1] != SOI:
        jpg.errors.append("missing SOI marker")
        return jpg

    jpg.segments.append(Segment(0, SOI, "SOI", 0, b""))
    pos = 2

    while pos < n - 1:
        if data[pos] != 0xFF:
            jpg.errors.append(f"expected a marker at offset {pos}, found 0x{data[pos]:02x}")
            break

        # Runs of 0xFF are legal padding before a marker.
        m = pos + 1
        while m < n and data[m] == 0xFF:
            m += 1
        if m >= n:
            jpg.errors.append("file ends inside a marker")
            break

        marker = data[m]
        name = MARKER_NAMES.get(marker, f"UNK{marker:02X}")

        if marker == EOI:
            jpg.segments.append(Segment(pos, EOI, "EOI", 0, b""))
            jpg.eoi_end = m + 1
            break

        if marker in STANDALONE:
            jpg.segments.append(Segment(pos, marker, name, 0, b""))
            pos = m + 1
            continue

        if m + 3 > n:
            jpg.errors.append(f"truncated length field at offset {m}")
            break

        (length,) = struct.unpack(">H", data[m + 1:m + 3])
        if length < 2:
            jpg.errors.append(f"segment {name} at {pos} declares an impossible length {length}")
            break
        payload = data[m + 3:m + 1 + length]
        jpg.segments.append(Segment(pos, marker, name, length, payload))

        pos = m + 1 + length

        if marker == 0xDA:  # SOS -> entropy-coded data follows
            block = _scan_entropy(data, pos)
            jpg.scans.append(block)
            pos = block.end

    if jpg.eoi_end is None and not jpg.errors:
        jpg.errors.append("no EOI marker found")

    return jpg


def strip_to_eoi(data: bytes) -> bytes:
    """Return the JPEG up to and including EOI, discarding trailing bytes."""
    jpg = parse_jpeg(data)
    if jpg.eoi_end is None:
        return data
    return data[:jpg.eoi_end]


# --------------------------------------------------------------------------
# Baseline-sequential entropy decoding
# --------------------------------------------------------------------------
#
# Byte accounting alone cannot find padding appended to a scan.  A scan has
# no declared length: it ends wherever the next marker begins.  Append bytes
# that contain no 0xFF and the scan walk simply absorbs them, because from
# the outside they are indistinguishable from compressed data.
#
# The only way to know where the entropy-coded data *actually* ends is to
# decode it and see where the last MCU finishes.  That is what this section
# does.  It also gives us the DCT coefficients, which the C-group JPEG-domain
# labs need, so the cost is paid once.
#
# Baseline sequential (SOF0) only.  Progressive scans are returned as
# unsupported rather than guessed at.

class EndOfScan(Exception):
    pass


class _BitReader:
    """MSB-first bit reader over a byte-stuffed entropy stream.

    `limit` bounds the reader to one scan. Progressive files have several
    scans, and a reader that runs past its own scan's end starts decoding the
    next scan's header as if it were entropy data -- which produces plausible
    coefficients and is completely wrong.

    Past the limit the reader returns zero bits rather than raising, which is
    what libjpeg does: an encoder is allowed to stop early and let the decoder
    pad, so hitting the end is normal termination, not an error.
    """

    __slots__ = ("data", "pos", "buf", "cnt", "limit", "exhausted")

    def __init__(self, data: bytes, pos: int, limit: Optional[int] = None):
        self.data = data
        self.pos = pos
        self.buf = 0
        self.cnt = 0
        self.limit = len(data) if limit is None else limit
        self.exhausted = False

    def read_bit(self) -> int:
        if self.cnt == 0:
            if self.pos >= self.limit:
                self.exhausted = True
                return 0
            b = self.data[self.pos]
            self.pos += 1
            if b == 0xFF:
                if self.pos >= len(self.data):
                    self.exhausted = True
                    return 0
                nxt = self.data[self.pos]
                if nxt == 0x00:
                    self.pos += 1          # stuffed byte
                else:
                    self.pos -= 1
                    self.exhausted = True
                    return 0
            self.buf = b
            self.cnt = 8
        self.cnt -= 1
        return (self.buf >> self.cnt) & 1

    def receive(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | self.read_bit()
        return v

    def align(self) -> None:
        self.cnt = 0

    def at_restart(self) -> bool:
        self.align()
        return (self.pos + 1 < len(self.data)
                and self.data[self.pos] == 0xFF
                and 0xD0 <= self.data[self.pos + 1] <= 0xD7)

    def try_restart(self) -> bool:
        self.align()
        if (self.pos + 1 < len(self.data)
                and self.data[self.pos] == 0xFF
                and 0xD0 <= self.data[self.pos + 1] <= 0xD7):
            self.pos += 2
            return True
        return False


def _build_huffman(bits: List[int], huffval: List[int]) -> Dict[tuple, int]:
    table: Dict[tuple, int] = {}
    code = 0
    k = 0
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            table[(length, code)] = huffval[k]
            k += 1
            code += 1
        code <<= 1
    return table


def _decode_symbol(reader: "_BitReader", table: Dict[tuple, int]) -> int:
    code = 0
    for length in range(1, 17):
        code = (code << 1) | reader.read_bit()
        if (length, code) in table:
            return table[(length, code)]
    if reader.exhausted:
        return 0
    raise EndOfScan("no Huffman code matched in 16 bits")


def _extend(v: int, n: int) -> int:
    if n == 0:
        return 0
    return v - (1 << n) + 1 if v < (1 << (n - 1)) else v


@dataclass
class ScanDecode:
    supported: bool
    reason: str = ""
    mcus_decoded: int = 0
    mcus_expected: int = 0
    consumed_end: Optional[int] = None   # first byte offset AFTER the last MCU
    physical_end: Optional[int] = None   # where the scan walk stopped
    coefficients: Optional[Dict[int, "np.ndarray"]] = None  # component id -> blocks

    @property
    def surplus(self) -> Optional[int]:
        if self.consumed_end is None or self.physical_end is None:
            return None
        return self.physical_end - self.consumed_end


def _frame_info(jpg: "JpegFile"):
    """Frame geometry and the per-component block grid dimensions."""
    sofs = [sg for sg in jpg.segments if sg.marker in SOF_MARKERS]
    if not sofs:
        return None, "no SOF segment"
    sof = sofs[0]
    if sof.marker not in (0xC0, 0xC2):
        return None, (f"only baseline SOF0 and progressive SOF2 are supported, "
                      f"found {MARKER_NAMES.get(sof.marker)}")

    body = sof.data
    height, width = struct.unpack(">HH", body[1:5])
    comps = []
    for i in range(body[5]):
        cid, hv, tq = body[6 + i * 3], body[7 + i * 3], body[8 + i * 3]
        comps.append({"id": cid, "h": hv >> 4, "v": hv & 0x0F, "tq": tq})

    hmax = max(c["h"] for c in comps)
    vmax = max(c["v"] for c in comps)
    mcux = (width + 8 * hmax - 1) // (8 * hmax)
    mcuy = (height + 8 * vmax - 1) // (8 * vmax)

    for comp in comps:
        # Two block counts per component, and conflating them is the classic
        # progressive bug. An interleaved scan walks MCUs, so it addresses
        # mcux * h blocks per row including padding past the image edge. A
        # non-interleaved scan walks the component's own grid, which stops at
        # the real edge. The grid is allocated at the padded size and the
        # non-interleaved walk uses the smaller one.
        comp["cols_padded"] = mcux * comp["h"]
        comp["rows_padded"] = mcuy * comp["v"]
        comp["cols"] = (width * comp["h"] // hmax + 7) // 8
        comp["rows"] = (height * comp["v"] // vmax + 7) // 8

    return {"width": width, "height": height, "comps": comps,
            "hmax": hmax, "vmax": vmax, "mcux": mcux, "mcuy": mcuy,
            "progressive": sof.marker == 0xC2}, ""


def _huffman_tables(jpg: "JpegFile", upto: int) -> tuple:
    """Tables defined before byte offset `upto`.

    Progressive files redefine tables between scans, so a decoder that reads
    every DHT in the file up front will use a later scan's table for an earlier
    scan. The tables are therefore rebuilt per scan from the segments that
    precede it.
    """
    dc: Dict[int, Dict[tuple, int]] = {}
    ac: Dict[int, Dict[tuple, int]] = {}
    for seg in jpg.segments_of("DHT"):
        if seg.offset > upto:
            continue
        buf = seg.data
        i = 0
        while i < len(buf):
            tc, th = buf[i] >> 4, buf[i] & 0x0F
            bits = list(buf[i + 1:i + 17])
            total = sum(bits)
            huffval = list(buf[i + 17:i + 17 + total])
            (ac if tc else dc)[th] = _build_huffman(bits, huffval)
            i += 17 + total
    return dc, ac


def _scan_params(seg: "Segment") -> Dict:
    body = seg.data
    ns = body[0]
    comps = []
    for i in range(ns):
        comps.append({"id": body[1 + i * 2],
                      "dc": body[2 + i * 2] >> 4,
                      "ac": body[2 + i * 2] & 0x0F})
    return {"comps": comps, "ss": body[1 + 2 * ns], "se": body[2 + 2 * ns],
            "ah": body[3 + 2 * ns] >> 4, "al": body[3 + 2 * ns] & 0x0F}


class _ProgressiveState:
    """Per-scan decoding state: DC predictors and the end-of-band run."""

    def __init__(self, comps):
        self.pred = {c["id"]: 0 for c in comps}
        self.eobrun = 0

    def restart(self):
        for k in self.pred:
            self.pred[k] = 0
        self.eobrun = 0


def _decode_dc_first(reader, block, table, state, cid, al):
    t = _decode_symbol(reader, table)
    diff = _extend(reader.receive(t), t) if t else 0
    state.pred[cid] += diff
    block[0] = state.pred[cid] << al


def _decode_dc_refine(reader, block, al):
    if reader.read_bit():
        block[0] |= (1 << al)


def _decode_ac_first(reader, block, table, state, ss, se, al):
    if state.eobrun > 0:
        state.eobrun -= 1
        return
    k = ss
    while k <= se:
        rs = _decode_symbol(reader, table)
        size, run = rs & 0x0F, rs >> 4
        if size == 0:
            if run < 15:
                state.eobrun = (1 << run) - 1
                if run:
                    state.eobrun += reader.receive(run)
                break
            k += 16
            continue
        k += run
        if k > 63:
            break
        block[k] = _extend(reader.receive(size), size) << al
        k += 1


def _decode_ac_refine(reader, block, table, state, ss, se, al):
    """The successive-approximation correction pass.

    This is the part of JPEG that is genuinely intricate, and the shape is
    worth stating because reading the code alone does not give it: every
    coefficient that is ALREADY non-zero receives one correction bit, in
    order, interleaved with the run-length symbols that introduce newly
    non-zero ones. A decoder that reads the correction bits in the wrong order
    relative to the run symbols produces coefficients that are individually
    plausible and collectively wrong.
    """
    p1 = 1 << al
    m1 = -1 << al
    k = ss

    if state.eobrun == 0:
        while k <= se:
            rs = _decode_symbol(reader, table)
            size, run = rs & 0x0F, rs >> 4
            value = 0
            if size == 0:
                if run < 15:
                    state.eobrun = 1 << run
                    if run:
                        state.eobrun += reader.receive(run)
                    break
            else:
                value = p1 if reader.read_bit() else m1

            while k <= se:
                if block[k] != 0:
                    if reader.read_bit() and (block[k] & p1) == 0:
                        block[k] += p1 if block[k] >= 0 else m1
                else:
                    if run == 0:
                        if value:
                            block[k] = value
                        break
                    run -= 1
                k += 1
            k += 1

    if state.eobrun > 0:
        while k <= se:
            if block[k] != 0:
                if reader.read_bit() and (block[k] & p1) == 0:
                    block[k] += p1 if block[k] >= 0 else m1
            k += 1
        state.eobrun -= 1


def decode_scan(jpg: "JpegFile", collect_coefficients: bool = False) -> ScanDecode:
    """Decode a JPEG's entropy-coded data into DCT coefficients.

    Handles baseline sequential (SOF0, one scan) and progressive (SOF2, many
    scans with spectral selection and successive approximation). Progressive
    support closes gap G-6; it is validated by the observation that a baseline
    and a progressive encoding of the same image with the same quantisation
    tables must yield bit-identical coefficients.
    """
    import numpy as np

    info, reason = _frame_info(jpg)
    if info is None:
        return ScanDecode(False, reason)

    sos_segments = jpg.segments_of("SOS")
    if not sos_segments:
        return ScanDecode(False, "no SOS segment")
    if len(sos_segments) != len(jpg.scans):
        return ScanDecode(False, f"{len(sos_segments)} SOS segments but "
                                 f"{len(jpg.scans)} entropy blocks")
    if not info["progressive"] and len(jpg.scans) != 1:
        return ScanDecode(False, f"baseline with {len(jpg.scans)} scans")

    comps = info["comps"]
    grids = {c["id"]: np.zeros((c["rows_padded"], c["cols_padded"], 64),
                               dtype=np.int32) for c in comps}
    by_id = {c["id"]: c for c in comps}

    restart_interval = 0
    for seg in jpg.segments_of("DRI"):
        if len(seg.data) >= 2:
            restart_interval = struct.unpack(">H", seg.data[:2])[0]

    total_units = 0
    last_consumed = None
    for seg, block in zip(sos_segments, jpg.scans):
        params = _scan_params(seg)
        dc_tables, ac_tables = _huffman_tables(jpg, seg.offset)
        reader = _BitReader(jpg.data, block.start, block.end)
        state = _ProgressiveState(comps)
        ss, se, ah, al = params["ss"], params["se"], params["ah"], params["al"]
        scan_comps = [by_id[c["id"]] for c in params["comps"] if c["id"] in by_id]
        if len(scan_comps) != len(params["comps"]):
            return ScanDecode(False, "scan references an unknown component")

        try:
            # Non-interleaved single-component walk, PROGRESSIVE ONLY. A
            # baseline file with one component also has a single-component
            # scan, but its blocks carry DC and AC together; routing it here
            # decoded the DC and never consumed the AC bits, which desynced
            # the stream from the second block onward and left every AC at
            # zero. The values looked plausible -- a smooth increasing DC ramp
            # -- and the encoder round-trip still passed, because encode and
            # decode shared the same wrong convention and reproduced the file
            # byte for byte.
            if info["progressive"] and len(scan_comps) == 1:
                comp = scan_comps[0]
                sel = params["comps"][0]
                grid = grids[comp["id"]]
                units = comp["rows"] * comp["cols"]
                for n in range(units):
                    if restart_interval and n and n % restart_interval == 0:
                        if reader.at_restart():
                            reader.try_restart()
                            state.restart()
                    blk = grid[n // comp["cols"], n % comp["cols"]]
                    if ss == 0:
                        if ah == 0:
                            _decode_dc_first(reader, blk, dc_tables[sel["dc"]],
                                             state, comp["id"], al)
                        else:
                            _decode_dc_refine(reader, blk, al)
                    else:
                        table = ac_tables[sel["ac"]]
                        if ah == 0:
                            _decode_ac_first(reader, blk, table, state, ss, se, al)
                        else:
                            _decode_ac_refine(reader, blk, table, state, ss, se, al)
                total_units += units
            else:
                units = info["mcux"] * info["mcuy"]
                for n in range(units):
                    if restart_interval and n and n % restart_interval == 0:
                        if reader.at_restart():
                            reader.try_restart()
                            state.restart()
                    my, mx = divmod(n, info["mcux"])
                    for sel in params["comps"]:
                        comp = by_id[sel["id"]]
                        grid = grids[comp["id"]]
                        for v in range(comp["v"]):
                            for hh in range(comp["h"]):
                                blk = grid[my * comp["v"] + v,
                                           mx * comp["h"] + hh]
                                if info["progressive"]:
                                    if ss == 0 and ah == 0:
                                        _decode_dc_first(reader, blk,
                                                         dc_tables[sel["dc"]],
                                                         state, comp["id"], al)
                                    elif ss == 0:
                                        _decode_dc_refine(reader, blk, al)
                                    else:
                                        return ScanDecode(
                                            False, "interleaved AC scan is "
                                                   "forbidden by the standard")
                                else:
                                    _decode_dc_first(reader, blk,
                                                     dc_tables[sel["dc"]],
                                                     state, comp["id"], 0)
                                    _decode_ac_first(reader, blk,
                                                     ac_tables[sel["ac"]],
                                                     state, 1, 63, 0)
                total_units += units
        except (EndOfScan, KeyError) as exc:
            return ScanDecode(False, f"scan decode failed: {exc}",
                              mcus_decoded=total_units)
        # Where the entropy decoder actually stopped, as against where the
        # scan physically ends. Lab 06 reads the difference: bytes inside a
        # scan that no decoder consumes are a place to hide things.
        reader.align()
        last_consumed = reader.pos

    # Flatten to MCU order, which is the contract every caller already depends on.
    result = ScanDecode(
        supported=True,
        mcus_decoded=info["mcux"] * info["mcuy"],
        mcus_expected=info["mcux"] * info["mcuy"],
        consumed_end=last_consumed,
        physical_end=jpg.scans[-1].end,
    )

    if collect_coefficients:
        out = {}
        for comp in comps:
            grid = grids[comp["id"]]
            blocks = []
            for my in range(info["mcuy"]):
                for mx in range(info["mcux"]):
                    for v in range(comp["v"]):
                        for hh in range(comp["h"]):
                            blocks.append(grid[my * comp["v"] + v,
                                               mx * comp["h"] + hh])
            out[comp["id"]] = np.array(blocks, dtype=np.int32)
        result.coefficients = out
    return result


def strip_to_eoi(data: bytes) -> bytes:
    """Return the JPEG up to and including EOI, discarding trailing bytes."""
    jpg = parse_jpeg(data)
    if jpg.eoi_end is None:
        return data
    return data[:jpg.eoi_end]


# --------------------------------------------------------------------------
# Baseline-sequential entropy decoding
# --------------------------------------------------------------------------
#
# Byte accounting alone cannot find padding appended to a scan.  A scan has
# no declared length: it ends wherever the next marker begins.  Append bytes
# that contain no 0xFF and the scan walk simply absorbs them, because from
# the outside they are indistinguishable from compressed data.
#
# The only way to know where the entropy-coded data *actually* ends is to
# decode it and see where the last MCU finishes.  That is what this section
# does.  It also gives us the DCT coefficients, which the C-group JPEG-domain
# labs need, so the cost is paid once.
#
# Baseline sequential (SOF0) only.  Progressive scans are returned as
# unsupported rather than guessed at.

class EndOfScan(Exception):
    pass


class _BitReader:
    """MSB-first bit reader over a byte-stuffed entropy stream.

    `limit` bounds the reader to one scan. Progressive files have several
    scans, and a reader that runs past its own scan's end starts decoding the
    next scan's header as if it were entropy data -- which produces plausible
    coefficients and is completely wrong.

    Past the limit the reader returns zero bits rather than raising, which is
    what libjpeg does: an encoder is allowed to stop early and let the decoder
    pad, so hitting the end is normal termination, not an error.
    """

    __slots__ = ("data", "pos", "buf", "cnt", "limit", "exhausted")

    def __init__(self, data: bytes, pos: int, limit: Optional[int] = None):
        self.data = data
        self.pos = pos
        self.buf = 0
        self.cnt = 0
        self.limit = len(data) if limit is None else limit
        self.exhausted = False

    def read_bit(self) -> int:
        if self.cnt == 0:
            if self.pos >= self.limit:
                self.exhausted = True
                return 0
            b = self.data[self.pos]
            self.pos += 1
            if b == 0xFF:
                if self.pos >= len(self.data):
                    self.exhausted = True
                    return 0
                nxt = self.data[self.pos]
                if nxt == 0x00:
                    self.pos += 1          # stuffed byte
                else:
                    self.pos -= 1
                    self.exhausted = True
                    return 0
            self.buf = b
            self.cnt = 8
        self.cnt -= 1
        return (self.buf >> self.cnt) & 1

    def receive(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | self.read_bit()
        return v

    def align(self) -> None:
        self.cnt = 0

    def at_restart(self) -> bool:
        self.align()
        return (self.pos + 1 < len(self.data)
                and self.data[self.pos] == 0xFF
                and 0xD0 <= self.data[self.pos + 1] <= 0xD7)

    def try_restart(self) -> bool:
        self.align()
        if (self.pos + 1 < len(self.data)
                and self.data[self.pos] == 0xFF
                and 0xD0 <= self.data[self.pos + 1] <= 0xD7):
            self.pos += 2
            return True
        return False


def _build_huffman(bits: List[int], huffval: List[int]) -> Dict[tuple, int]:
    table: Dict[tuple, int] = {}
    code = 0
    k = 0
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            table[(length, code)] = huffval[k]
            k += 1
            code += 1
        code <<= 1
    return table


def _decode_symbol(reader: "_BitReader", table: Dict[tuple, int]) -> int:
    code = 0
    for length in range(1, 17):
        code = (code << 1) | reader.read_bit()
        if (length, code) in table:
            return table[(length, code)]
    if reader.exhausted:
        return 0
    raise EndOfScan("no Huffman code matched in 16 bits")


def _extend(v: int, n: int) -> int:
    if n == 0:
        return 0
    return v - (1 << n) + 1 if v < (1 << (n - 1)) else v


@dataclass
class ScanDecode:
    supported: bool
    reason: str = ""
    mcus_decoded: int = 0
    mcus_expected: int = 0
    consumed_end: Optional[int] = None   # first byte offset AFTER the last MCU
    physical_end: Optional[int] = None   # where the scan walk stopped
    coefficients: Optional[Dict[int, "np.ndarray"]] = None  # component id -> blocks

    @property
    def surplus(self) -> Optional[int]:
        if self.consumed_end is None or self.physical_end is None:
            return None
        return self.physical_end - self.consumed_end

