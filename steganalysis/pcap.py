"""From-scratch pcap handling, and seeded traffic.

Same rule as every other parser here: nothing asks a decoder what a capture
contains. This walks the record stream and reports what is physically present,
including fields no application would ever read.

Network carriers differ from every file carrier in one way that shapes the
whole lab. A file is a finished object an analyst holds; a capture is a
*sample* of a conversation that was already in progress and continued after the
capture stopped. Everything measured here is measured on a window, and the
window's length is part of every statistic -- twenty DNS queries in a capture is
meaningless without knowing whether the capture is one second or one hour.

Traffic is generated from seeds like the image and audio corpora, and for the
same reason: nothing binary in the repository, and "same source" stays a
checkable property. The generated traffic deliberately includes the things that
make network steganalysis hard -- high-entropy CDN hostnames, repeated cached
lookups, jittered inter-arrival times -- because a corpus of tidy traffic would
make the detectors look far better than they are.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

PCAP_MAGIC = 0xA1B2C3D4
LINKTYPE_ETHERNET = 1


@dataclass
class Packet:
    """One captured frame, parsed as far as the transport layer."""

    index: int
    timestamp: float
    raw: bytes
    src_ip: str = ""
    dst_ip: str = ""
    protocol: int = 0
    ip_id: int = 0
    dont_fragment: bool = False
    src_port: int = 0
    dst_port: int = 0
    tcp_seq: int = 0
    tcp_flags: int = 0
    payload: bytes = b""

    @property
    def is_tcp(self) -> bool:
        return self.protocol == 6

    @property
    def is_udp(self) -> bool:
        return self.protocol == 17

    @property
    def is_dns_query(self) -> bool:
        return self.is_udp and self.dst_port == 53


@dataclass
class Capture:
    packets: List[Packet] = field(default_factory=list)
    linktype: int = LINKTYPE_ETHERNET
    errors: List[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.packets)

    @property
    def duration(self) -> float:
        if len(self.packets) < 2:
            return 0.0
        return self.packets[-1].timestamp - self.packets[0].timestamp

    def inter_arrivals(self) -> np.ndarray:
        times = np.array([p.timestamp for p in self.packets])
        return np.diff(times) if times.size > 1 else np.array([])

    def dns_queries(self) -> List[Packet]:
        return [p for p in self.packets if p.is_dns_query]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _parse_frame(raw: bytes, index: int, timestamp: float) -> Packet:
    pkt = Packet(index=index, timestamp=timestamp, raw=raw)
    if len(raw) < 14:
        return pkt
    ethertype = struct.unpack(">H", raw[12:14])[0]
    if ethertype != 0x0800 or len(raw) < 34:
        return pkt

    ihl = (raw[14] & 0x0F) * 4
    total_len = struct.unpack(">H", raw[16:18])[0]
    pkt.ip_id = struct.unpack(">H", raw[18:20])[0]
    flags_frag = struct.unpack(">H", raw[20:22])[0]
    pkt.dont_fragment = bool(flags_frag & 0x4000)
    pkt.protocol = raw[23]
    pkt.src_ip = ".".join(str(b) for b in raw[26:30])
    pkt.dst_ip = ".".join(str(b) for b in raw[30:34])

    transport = 14 + ihl
    if pkt.protocol == 6 and len(raw) >= transport + 20:
        pkt.src_port, pkt.dst_port = struct.unpack(">HH", raw[transport:transport + 4])
        pkt.tcp_seq = struct.unpack(">I", raw[transport + 4:transport + 8])[0]
        pkt.tcp_flags = raw[transport + 13]
        offset = (raw[transport + 12] >> 4) * 4
        pkt.payload = raw[transport + offset:14 + total_len]
    elif pkt.protocol == 17 and len(raw) >= transport + 8:
        pkt.src_port, pkt.dst_port = struct.unpack(">HH", raw[transport:transport + 4])
        pkt.payload = raw[transport + 8:14 + total_len]
    return pkt


def parse_pcap(data: bytes) -> Capture:
    """Walk a libpcap file. Malformed input yields errors, not exceptions."""
    cap = Capture()
    if len(data) < 24:
        cap.errors.append("truncated pcap header")
        return cap

    magic = struct.unpack("<I", data[:4])[0]
    if magic == PCAP_MAGIC:
        endian = "<"
    elif struct.unpack(">I", data[:4])[0] == PCAP_MAGIC:
        endian = ">"
    else:
        cap.errors.append(f"not a libpcap file (magic 0x{magic:08x})")
        return cap

    cap.linktype = struct.unpack(endian + "I", data[20:24])[0]
    pos = 24
    index = 0
    while pos + 16 <= len(data):
        ts_sec, ts_usec, incl, _orig = struct.unpack(endian + "IIII",
                                                     data[pos:pos + 16])
        pos += 16
        if pos + incl > len(data):
            cap.errors.append(f"record {index} claims {incl} bytes, file ends early")
            break
        cap.packets.append(_parse_frame(data[pos:pos + incl], index,
                                        ts_sec + ts_usec / 1e6))
        pos += incl
        index += 1
    return cap


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _ip_checksum(header: bytes) -> int:
    total = 0
    for i in range(0, len(header), 2):
        total += struct.unpack(">H", header[i:i + 2])[0]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_frame(src_ip: str, dst_ip: str, protocol: int, payload: bytes,
                ip_id: int = 0, src_port: int = 0, dst_port: int = 0,
                tcp_seq: int = 0, tcp_flags: int = 0x18,
                dont_fragment: bool = True) -> bytes:
    """One Ethernet/IPv4/(TCP|UDP) frame with a correct IPv4 checksum."""
    if protocol == 17:
        transport = struct.pack(">HHHH", src_port, dst_port,
                                8 + len(payload), 0) + payload
    else:
        transport = struct.pack(">HHIIBBHHH", src_port, dst_port, tcp_seq, 0,
                                0x50, tcp_flags, 8192, 0, 0) + payload

    total_len = 20 + len(transport)
    flags = 0x4000 if dont_fragment else 0
    header = struct.pack(">BBHHHBBH", 0x45, 0, total_len, ip_id, flags, 64,
                         protocol, 0)
    header += bytes(int(x) for x in src_ip.split("."))
    header += bytes(int(x) for x in dst_ip.split("."))
    header = header[:10] + struct.pack(">H", _ip_checksum(header)) + header[12:]

    eth = b"\x02\x00\x00\x00\x00\x01\x02\x00\x00\x00\x00\x02\x08\x00"
    return eth + header + transport


def write_pcap(frames: List[Tuple[float, bytes]]) -> bytes:
    """Serialise (timestamp, frame) pairs as a libpcap file."""
    out = bytearray(struct.pack("<IHHiIII", PCAP_MAGIC, 2, 4, 0, 0, 65535,
                                LINKTYPE_ETHERNET))
    for timestamp, frame in frames:
        sec = int(timestamp)
        usec = int(round((timestamp - sec) * 1e6))
        if usec >= 1_000_000:
            sec += 1
            usec -= 1_000_000
        out += struct.pack("<IIII", sec, usec, len(frame), len(frame))
        out += frame
    return bytes(out)


# --------------------------------------------------------------------------
# DNS
# --------------------------------------------------------------------------

def encode_dns_name(name: str) -> bytes:
    out = b""
    for label in name.split("."):
        if label:
            out += bytes([len(label)]) + label.encode("ascii")
    return out + b"\x00"


def decode_dns_name(payload: bytes, offset: int = 12) -> Tuple[str, int]:
    labels = []
    pos = offset
    while pos < len(payload):
        length = payload[pos]
        if length == 0:
            pos += 1
            break
        if length & 0xC0:                      # compression pointer
            pos += 2
            break
        labels.append(payload[pos + 1:pos + 1 + length].decode("ascii", "replace"))
        pos += 1 + length
    return ".".join(labels), pos


def build_dns_query(name: str, txid: int = 0x1234, qtype: int = 1) -> bytes:
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    return header + encode_dns_name(name) + struct.pack(">HH", qtype, 1)


def query_name(pkt: Packet) -> str:
    if not pkt.is_dns_query or len(pkt.payload) < 13:
        return ""
    name, _ = decode_dns_name(pkt.payload)
    return name


# --------------------------------------------------------------------------
# Seeded traffic
# --------------------------------------------------------------------------

#: Hostnames a real capture contains: CDN shards and reputation lookups have
#: high-entropy labels and would trip a naive entropy detector, which is
#: exactly why they are in the corpus.
_BACKGROUND_NAMES = [
    "www.example.com", "api.example.com", "cdn.example.net",
    "d3k7l9m2n4p6q8.cloudfront.example", "a1b2c3d4e5f6.reputation.example",
    "mail.example.org", "ntp.example.org", "metrics.example.com",
    "static.example.net", "auth.example.com",
]


@dataclass
class TrafficSpec:
    name: str
    seed: int
    packets: int = 400
    seconds: float = 30.0
    dns_fraction: float = 0.25
    #: Share of DNS lookups that repeat a name already queried. Real resolvers
    #: cache, so repeats are the norm; a tunnel never repeats, and that gap is
    #: the single most useful DNS signal.
    repeat_fraction: float = 0.6


def render_traffic(spec: TrafficSpec) -> bytes:
    """Deterministically render one background capture."""
    rng = np.random.default_rng(spec.seed)
    frames: List[Tuple[float, bytes]] = []
    t = 1_700_000_000.0
    asked: List[str] = []
    ip_counter = int(rng.integers(1000, 60000))

    for i in range(spec.packets):
        # Log-normal gaps: bursty, continuous, no preferred value.
        t += float(rng.lognormal(mean=np.log(spec.seconds / spec.packets),
                                 sigma=0.8))
        if rng.random() < spec.dns_fraction:
            if asked and rng.random() < spec.repeat_fraction:
                name = asked[int(rng.integers(0, len(asked)))]
            else:
                name = _BACKGROUND_NAMES[int(rng.integers(0, len(_BACKGROUND_NAMES)))]
                asked.append(name)
            frame = build_frame("10.0.0.5", "10.0.0.1", 17,
                                build_dns_query(name, int(rng.integers(0, 65535))),
                                ip_id=0, src_port=int(rng.integers(1024, 65535)),
                                dst_port=53)
        else:
            ip_counter = (ip_counter + 1) & 0xFFFF
            frame = build_frame("10.0.0.5", "93.184.216.34", 6,
                                bytes(rng.integers(0, 256, int(rng.integers(0, 400)),
                                                   dtype=np.uint8)),
                                ip_id=0, src_port=44000,
                                dst_port=443, tcp_seq=int(rng.integers(0, 2**32)))
        frames.append((t, frame))
    return write_pcap(frames)


def default_traffic_specs(n: int = 16, seed0: int = 90_000) -> List[TrafficSpec]:
    return [TrafficSpec(name=f"bg_{i:03d}.pcap", seed=seed0 + i,
                        packets=400, seconds=30.0,
                        dns_fraction=[0.15, 0.25, 0.35][i % 3],
                        repeat_fraction=[0.5, 0.6, 0.75][i % 3])
            for i in range(n)]
