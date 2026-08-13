"""H-group tests: network carriers.

The parser test cross-validates against tshark when it is installed and skips
cleanly when it is not, so the suite stays honest on a minimal machine rather
than silently testing one implementation against itself.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402
from steganalysis.pcap import (TrafficSpec, parse_pcap, query_name,  # noqa: E402
                               render_traffic)


def background(seed: int, packets: int = 1200, seconds: float = 90.0) -> bytes:
    return render_traffic(TrafficSpec(f"bg{seed}.pcap", seed, packets=packets,
                                      seconds=seconds))


def payload(nbytes: int, seed: int) -> bytes:
    return np.random.default_rng(seed).integers(
        0, 256, nbytes, dtype=np.uint8).tobytes()


# ------------------------------------------------------------------ parser

def test_parser_round_trips_its_own_output():
    cap = parse_pcap(background(92_001, packets=200, seconds=10.0))
    assert cap.errors == []
    assert len(cap) == 200
    assert cap.duration > 0
    assert all(p.dst_port in (53, 443) for p in cap.packets)


@pytest.mark.skipif(shutil.which("tshark") is None, reason="tshark not installed")
def test_parser_agrees_with_tshark():
    """An independent implementation, as gate G1 does with pngcheck and djpeg."""
    blob = background(92_002, packets=300, seconds=20.0)
    cap = parse_pcap(blob)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "c.pcap"
        path.write_bytes(blob)
        out = subprocess.run(
            ["tshark", "-r", str(path), "-T", "fields", "-e", "frame.number",
             "-e", "ip.id", "-e", "ip.proto", "-e", "dns.qry.name",
             "-e", "ip.flags.df", "-e", "tcp.seq_raw"],
            capture_output=True, text=True)
        assert out.returncode == 0, out.stderr[:200]
        rows = [line.split("\t") for line in out.stdout.strip().split("\n")]

    assert len(rows) == len(cap)
    for row in rows:
        pkt = cap.packets[int(row[0]) - 1]
        if row[1]:
            assert int(row[1], 16) == pkt.ip_id
        if row[2]:
            assert int(row[2]) == pkt.protocol
        if row[3]:
            assert row[3] == query_name(pkt)
        if row[4]:
            assert (row[4] == "True") == pkt.dont_fragment
        if len(row) > 5 and row[5]:
            assert int(row[5]) == pkt.tcp_seq


@pytest.mark.skipif(shutil.which("tshark") is None, reason="tshark not installed")
def test_generated_ipv4_checksums_are_valid():
    blob = background(92_003, packets=100, seconds=10.0)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "c.pcap"
        path.write_bytes(blob)
        out = subprocess.run(
            ["tshark", "-r", str(path), "-o", "ip.check_checksum:TRUE",
             "-T", "fields", "-e", "ip.checksum.status"],
            capture_output=True, text=True)
    statuses = [s for s in out.stdout.split("\n") if s]
    assert statuses and set(statuses) == {"1"}, set(statuses)


# ------------------------------------------------------------------ lab 21

@pytest.mark.parametrize("variant,size", [("dns_tunnel", 2000),
                                          ("ip_id", 200), ("timing", 100)])
def test_each_channel_round_trips_and_is_detected(variant, size):
    lab = load_lab("21_network")
    data = payload(size, 31)
    stego = lab.embed(background(92_010), data, variant=variant)
    assert lab.detect(stego, "s", baseline=None).verdict >= Evidence.E1

    extract = {"dns_tunnel": lambda: lab.extract_dns_tunnel(stego),
               "ip_id": lambda: lab.extract_ip_id(stego, size),
               "timing": lambda: lab.extract_timing(stego, size)}[variant]
    assert extract() == data


def test_background_traffic_is_not_reported():
    lab = load_lab("21_network")
    alarms = sum(1 for i in range(8)
                 if lab.detect(background(92_020 + i), "bg",
                               baseline=None).verdict >= Evidence.E1)
    assert alarms == 0, f"{alarms}/8 false positives"


def test_dns_needs_volume_uniqueness_and_length_together():
    """Background exceeds the rate threshold; uniqueness is what rejects it."""
    lab = load_lab("21_network")
    profile = lab.dns_profile(parse_pcap(background(92_030)))
    busiest = max(profile, key=lambda d: d["queries"])
    assert busiest["per_minute"] > 20, "background should be busy"
    assert busiest["unique_ratio"] < 0.5, "resolvers cache, so traffic repeats"
    assert lab.detect(background(92_030), "bg", baseline=None).verdict == Evidence.E0


def test_timing_channel_quantises_where_jitter_does_not():
    lab = load_lab("21_network")
    clean = lab.timing_profile(parse_pcap(background(92_040)))
    stego = lab.timing_profile(parse_pcap(
        lab.embed(background(92_040), payload(100, 32), variant="timing")))
    assert clean["top_two_share"] < 0.1
    assert stego["top_two_share"] > 0.5


def test_ip_id_stops_at_e1_because_a_randomising_stack_looks_the_same():
    """The ceiling is the finding, not a limitation to be fixed later."""
    lab = load_lab("21_network")
    stego = lab.embed(background(92_050), payload(200, 33), variant="ip_id")
    report = lab.detect(stego, "s", baseline=None)
    ip_findings = [f for f in report.findings if f.detector == "ip_id_entropy"]
    assert ip_findings
    assert all(f.level == Evidence.E1 for f in ip_findings)
    assert "randomising" in ip_findings[0].claim or "mind" in ip_findings[0].claim


def test_repetitive_payload_defeats_the_uniqueness_signal():
    """A real hole, asserted so it cannot be quietly forgotten.

    An unsophisticated sender who does not compress accidentally evades a
    detector aimed at sophisticated ones.
    """
    lab = load_lab("21_network")
    bg = background(92_060)
    random_run = lab.embed(bg, payload(2000, 34), variant="dns_tunnel")
    repeated = lab.embed(bg, b"x" * 2000, variant="dns_tunnel")

    def unique_ratio(blob):
        entries = [d for d in lab.dns_profile(parse_pcap(blob))
                   if d["domain"] == "tunnel.example"]
        return entries[0]["unique_ratio"] if entries else 0.0

    assert unique_ratio(random_run) > 0.9
    assert unique_ratio(repeated) < 0.1
    assert lab.detect(repeated, "s", baseline=None).verdict == Evidence.E0


def test_reaches_e4_with_a_baseline():
    lab = load_lab("21_network")
    data = payload(2000, 35)
    stego = lab.embed(background(92_070), data, variant="dns_tunnel")
    baseline = FalsePositiveBaseline("dns_tunnel", 12, 0, 30.0,
                                     "12 seeded background captures")
    report = lab.detect(stego, "s", baseline=baseline)
    assert report.verdict == Evidence.E4
    assert any(f.payload == data for f in report.findings)


def test_capacity_is_enforced():
    lab = load_lab("21_network")
    with pytest.raises(ValueError, match="payload needs"):
        lab.embed(background(92_080, packets=50, seconds=5.0),
                  payload(500, 36), variant="timing")
