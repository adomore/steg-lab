"""Lab 21 -- network carriers, where the carrier keeps moving.

Three channels, chosen because each fails differently and each has a
legitimate twin that makes naive detection useless:

  * **DNS tunnelling** -- payload in query labels. The twin is CDN sharding and
    reputation lookups, whose hostnames are long, random-looking and perfectly
    innocent.
  * **IP identification** -- payload in the 16-bit IP ID field. The twin is
    every operating system that randomises it; Linux writes zero for atomic
    datagrams, and other stacks count or randomise.
  * **Inter-packet timing** -- payload in the gaps between packets. The twin is
    ordinary network jitter, which is large, continuous and unpredictable.

What separates a network carrier from every file carrier in this repository is
that there is no file. A capture is a *window* onto a conversation that started
before it and continued after. Every count here is meaningless without its
duration, and a detector that reports "twenty suspicious queries" without
saying over what interval has reported nothing.

Domain    : network
Algorithm : dns-tunnel / ip-id / inter-packet-timing
"""

from __future__ import annotations

import base64
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)
from steganalysis.pcap import (Capture, _ip_checksum, build_dns_query,
                               build_frame, parse_pcap, query_name, write_pcap)

NAME = "network"
DOMAIN = "network"
ALGORITHM = "dns-tunnel"

#: Label length in base32 characters. Below the 63-octet DNS label limit with
#: room for the encoding overhead.
LABEL_CHARS = 40

#: Queries to one registered domain, per minute of capture, before the volume
#: is worth a second look on its own. A rate, not a count: a capture is a
#: window, and a count without its window is not a measurement.
QUERIES_PER_MINUTE = 30.0

#: Share of queries to a domain that are first-time lookups. Resolvers cache,
#: so real traffic repeats heavily; a tunnel never repeats because every query
#: carries different bytes. This is the strongest single DNS signal here.
UNIQUE_RATIO = 0.9

#: Distinct rounded inter-arrival values below which the timing looks
#: quantised rather than jittered.
TIMING_DISTINCT = 12


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def registered_domain(name: str) -> str:
    """The last two labels. Crude, and adequate for a lab corpus.

    A real deployment needs the public suffix list, because `example.co.uk`
    has three labels and `s3.amazonaws.com` behaves like a suffix. Getting this
    wrong splits one tunnel across many apparent domains and hides it, so the
    shortcut is recorded rather than left implicit.
    """
    parts = [p for p in name.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else name


# --------------------------------------------------------------------------
# Embedding
# --------------------------------------------------------------------------

def _frames_of(cap: Capture) -> List[tuple]:
    return [(p.timestamp, p.raw) for p in cap.packets]


def embed_dns_tunnel(background: bytes, payload: bytes,
                     domain: str = "tunnel.example",
                     src: str = "10.0.0.5") -> bytes:
    """Interleave tunnel queries into an existing capture.

    A covert channel rides on traffic; it does not replace it. An earlier
    version of this function produced a standalone capture of nothing but
    tunnel queries, and that fixture was wrong in a way that quietly corrupted
    the results: with only tunnel packets present, the capture's inter-arrival
    times were the embedder's fixed gap, so the TIMING detector fired on the
    DNS and IP-ID channels. The detector was right about what it saw; what it
    saw was an artefact of the test data.

    Injecting into background traffic also makes the measurement honest in the
    other direction, because the tunnel now has to be found among real queries
    rather than being the only thing there.
    """
    cap = parse_pcap(background)
    frames = _frames_of(cap)
    if not frames:
        raise ValueError("background capture is empty")

    encoded = base64.b32encode(payload).decode("ascii").rstrip("=").lower()
    chunks = [encoded[i:i + LABEL_CHARS]
              for i in range(0, len(encoded), LABEL_CHARS)] or [""]

    # Slot each query just after an existing packet, so the tunnel inherits the
    # capture's own timing rather than imposing a rhythm of its own.
    step = max(len(frames) // (len(chunks) + 1), 1)
    for i, chunk in enumerate(chunks):
        anchor = frames[min((i + 1) * step, len(frames) - 1)][0]
        frame = build_frame(src, "10.0.0.1", 17,
                            build_dns_query(f"{chunk}.{domain}", 0x1000 + i),
                            ip_id=0, src_port=40000 + (i % 20000), dst_port=53)
        frames.append((anchor + 0.001, frame))
    frames.sort(key=lambda f: f[0])
    return write_pcap(frames)


def extract_dns_tunnel(data: bytes, domain: str = "tunnel.example") -> bytes:
    """Keyless: the labels are the payload, in order."""
    cap = parse_pcap(data)
    encoded = ""
    for pkt in cap.dns_queries():
        name = query_name(pkt)
        if name.endswith(domain):
            encoded += name[: -(len(domain) + 1)]
    padding = "=" * (-len(encoded) % 8)
    try:
        return base64.b32decode(encoded.upper() + padding)
    except Exception:
        return b""


def embed_ip_id(background: bytes, payload: bytes) -> bytes:
    """Rewrite the IP ID of existing packets, leaving timing untouched."""
    cap = parse_pcap(background)
    padded = payload + (b"\x00" if len(payload) % 2 else b"")
    needed = len(padded) // 2
    targets = [p for p in cap.packets if p.dont_fragment and p.protocol == 6]
    if len(targets) < needed:
        raise ValueError(f"payload needs {needed} packets, capture has "
                         f"{len(targets)}")

    patched = {}
    for i, pkt in enumerate(targets[:needed]):
        ident = (padded[2 * i] << 8) | padded[2 * i + 1]
        raw = bytearray(pkt.raw)
        raw[18:20] = ident.to_bytes(2, "big")
        # The IPv4 checksum covers the identification field, so it has to be
        # recomputed. Leaving it stale would make every modified packet fail
        # verification in Wireshark -- a louder tell than the channel itself.
        raw[24:26] = b"\x00\x00"
        raw[24:26] = _ip_checksum(bytes(raw[14:34])).to_bytes(2, "big")
        patched[pkt.index] = bytes(raw)

    return write_pcap([(p.timestamp, patched.get(p.index, p.raw))
                       for p in cap.packets])


def extract_ip_id(data: bytes, nbytes: int) -> bytes:
    cap = parse_pcap(data)
    out = bytearray()
    for pkt in cap.packets:
        if not (pkt.dont_fragment and pkt.protocol == 6):
            continue
        out.append((pkt.ip_id >> 8) & 0xFF)
        out.append(pkt.ip_id & 0xFF)
        if len(out) >= nbytes:
            break
    return bytes(out[:nbytes])


def embed_timing(background: bytes, payload: bytes, short: float = 0.02,
                 long: float = 0.08) -> bytes:
    """Retime existing packets: a short gap is 0, a long one is 1.

    The packets and their contents are untouched; only when they leave
    changes. That is the property that makes timing channels survive protocol
    normalisation and content inspection alike.
    """
    cap = parse_pcap(background)
    bits = "".join(f"{byte:08b}" for byte in payload)
    if len(cap.packets) < len(bits) + 1:
        raise ValueError(f"payload needs {len(bits) + 1} packets, capture has "
                         f"{len(cap.packets)}")

    # Only the packets carrying bits are retimed; everything after keeps its
    # original spacing. An earlier version gave the tail a third fixed gap,
    # which diluted the quantisation the detector looks for and hid the
    # channel -- the embedder was making the traffic look MORE natural than a
    # real channel would, so the measurement flattered the embedder.
    frames = [(cap.packets[0].timestamp, cap.packets[0].raw)]
    t = cap.packets[0].timestamp
    original = cap.inter_arrivals()
    for i, pkt in enumerate(cap.packets[1:]):
        if i < len(bits):
            t += long if bits[i] == "1" else short
        else:
            t += float(original[i])
        frames.append((t, pkt.raw))
    return write_pcap(frames)


def extract_timing(data: bytes, nbytes: int, threshold: float = 0.05) -> bytes:
    cap = parse_pcap(data)
    gaps = cap.inter_arrivals()
    bits = "".join("1" if g > threshold else "0" for g in gaps)
    usable = min((len(bits) // 8) * 8, nbytes * 8)
    return bytes(int(bits[i:i + 8], 2) for i in range(0, usable, 8))


def embed(background: bytes, payload: bytes,
          variant: str = "dns_tunnel") -> bytes:
    """Every channel injects into a background capture. See embed_dns_tunnel."""
    if variant == "dns_tunnel":
        return embed_dns_tunnel(background, payload)
    if variant == "ip_id":
        return embed_ip_id(background, payload)
    if variant == "timing":
        return embed_timing(background, payload)
    raise ValueError(f"unknown variant {variant}")


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def dns_profile(cap: Capture) -> List[Dict[str, object]]:
    """Per registered domain: rate, uniqueness, label length and entropy."""
    minutes = max(cap.duration / 60.0, 1e-6)
    by_domain: Dict[str, List[str]] = {}
    for pkt in cap.dns_queries():
        name = query_name(pkt)
        if name:
            by_domain.setdefault(registered_domain(name), []).append(name)

    out = []
    for domain, names in by_domain.items():
        leading = [n.split(".")[0] for n in names]
        out.append({
            "domain": domain,
            "queries": len(names),
            "per_minute": len(names) / minutes,
            "unique_ratio": len(set(names)) / len(names),
            "mean_label_length": float(np.mean([len(l) for l in leading])),
            "mean_label_entropy": float(np.mean([_entropy(l) for l in leading])),
        })
    return sorted(out, key=lambda d: -d["queries"])


def ip_id_profile(cap: Capture) -> Dict[str, float]:
    """What the IP ID field is doing across the capture.

    Three behaviours are normal and one is not. Linux writes zero for atomic
    datagrams with DF set; older stacks use a global or per-destination
    counter, giving small consecutive deltas; some stacks randomise. Payload
    bytes give uniform 16-bit values with no zeros and no small deltas -- which
    is indistinguishable from a randomising stack, so this signal cannot stand
    on its own and the detector says so.
    """
    ids = np.array([p.ip_id for p in cap.packets if p.dont_fragment])
    if ids.size < 8:
        return {}
    nonzero = ids[ids != 0]
    # The signal is a MINORITY of odd packets, not a uniform property of the
    # capture. An earlier version required every DF packet to carry a non-zero
    # ID, which no real channel produces: an embedder writes into the packets
    # it needs and leaves the rest alone, so the anomaly is a subset. Requiring
    # it of the whole capture made the detector silent on exactly the case it
    # was written for.
    return {"packets": int(ids.size),
            "zero_fraction": float(np.mean(ids == 0)),
            "nonzero_packets": int(nonzero.size),
            "nonzero_unique_fraction": (float(len(set(nonzero.tolist())) / nonzero.size)
                                        if nonzero.size else 0.0),
            "mixed": bool(0 < nonzero.size < ids.size)}


def timing_profile(cap: Capture, places: int = 3) -> Dict[str, float]:
    """Is the inter-arrival distribution continuous or quantised?"""
    gaps = cap.inter_arrivals()
    if gaps.size < 8:
        return {}
    rounded = np.round(gaps, places)
    counts = Counter(rounded.tolist())
    top_two = sum(c for _v, c in counts.most_common(2))
    return {"gaps": int(gaps.size),
            "distinct_values": len(counts),
            "top_two_share": top_two / gaps.size,
            "coefficient_of_variation": float(np.std(gaps) / max(np.mean(gaps), 1e-12))}


def detect(data: bytes, name: str = "<capture>",
           baseline: Optional[FalsePositiveBaseline] = None,
           payload_bytes: int = 0) -> Report:
    report = Report(carrier=name)
    cap = parse_pcap(data)
    if not len(cap):
        return report

    # --- DNS. Volume, uniqueness, label shape -- all three, or none.
    for entry in dns_profile(cap):
        if entry["queries"] < 8:
            continue
        if not (entry["per_minute"] >= QUERIES_PER_MINUTE
                and entry["unique_ratio"] >= UNIQUE_RATIO
                and entry["mean_label_length"] >= 20):
            continue
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = extract_dns_tunnel(data, entry["domain"]) \
            if level >= Evidence.E3 else None
        if payload:
            level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="dns_tunnel",
            claim=(f"{entry['queries']} queries to '{entry['domain']}' at "
                   f"{entry['per_minute']:.0f}/min, "
                   f"{entry['unique_ratio']:.0%} of them first-time lookups, "
                   f"mean label {entry['mean_label_length']:.0f} characters at "
                   f"{entry['mean_label_entropy']:.1f} bits/char -- resolvers "
                   f"cache, so real traffic repeats"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="dns-tunnel" if level >= Evidence.E3 else None,
            payload=payload,
            baseline=baseline,
            detail={k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in entry.items()},
        ))

    # --- Timing. Quantised gaps where jitter should be continuous.
    timing = timing_profile(cap)
    # A timing channel need not cover the whole capture, so the test is on the
    # SHARE of gaps landing on a few values rather than on the capture having
    # few values overall. A channel occupying half a capture still puts half
    # its gaps on two numbers, which jitter never does.
    if timing and timing["top_two_share"] >= 0.5:
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = (extract_timing(data, payload_bytes or 64)
                   if level >= Evidence.E3 else None)
        if payload:
            level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="timing_channel",
            claim=(f"{timing['gaps']} inter-arrival gaps take only "
                   f"{timing['distinct_values']} distinct values, with "
                   f"{timing['top_two_share']:.0%} falling in the top two; "
                   f"network jitter is continuous"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="inter-packet-timing" if level >= Evidence.E3 else None,
            payload=payload,
            baseline=baseline,
            detail={k: round(v, 4) if isinstance(v, float) else v
                    for k, v in timing.items()},
        ))

    # --- IP ID. Reported at E1 only; see ip_id_profile for why.
    ipid = ip_id_profile(cap)
    if (ipid and ipid["mixed"] and ipid["nonzero_packets"] >= 8
            and ipid["nonzero_unique_fraction"] > 0.9
            and ipid["zero_fraction"] > 0.5):
        report.add(Finding(
            carrier=name, level=Evidence.E1, detector="ip_id_entropy",
            claim=(f"{ipid['nonzero_packets']} of {ipid['packets']} DF packets "
                   f"carry distinct non-zero IP IDs while the rest carry zero; "
                   f"one host does not usually change its mind about how it "
                   f"fills that field mid-capture"),
            detail={k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in ipid.items()},
        ))

    return report


def build_sample(background: bytes, payload: bytes,
                 variant: str = "dns_tunnel") -> bytes:
    return embed(background, payload, variant=variant)
