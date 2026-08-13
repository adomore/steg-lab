"""Lab 23 -- file slack, where the payload does not travel with the file.

A filesystem hands out storage in clusters. A file of N bytes with C-byte
clusters leaves C - (N mod C) bytes inside its last cluster that belong to its
allocation and hold none of its content. That is **file slack**.

Every carrier before this one was part of a file. Copy the file and the payload
comes along; email it and it arrives. Slack is a property of the **volume**.
Copy the file out and the payload stays behind. That single fact reorders the
whole examination: the evidence is the disk image, and a working copy of the
files is not a copy of the evidence.

**The discrimination problem is different too, and harder.** In every other lab
the question was whether an anomaly is a payload. Here non-zero slack has a
second, entirely innocent explanation that is not rare but *normal*: when a
file is deleted and a smaller one takes its cluster, the old file's tail
survives in the new file's slack. That is forensic residue, and finding it is
routine. The lab measures both cases rather than pretending the second does not
exist.

Domain    : filesystem
Algorithm : file-slack
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)
from steganalysis.extfs import ExtSlack, parse_ext
from steganalysis.ntfs import parse_ntfs
from steganalysis.fat import (FatVolume, SlackRegion, parse_fat, read_slack,
                              write_slack)

NAME = "filesystem"
DOMAIN = "filesystem"
ALGORITHM = "file-slack"

#: Bytes of non-zero content in one slack region before it is worth reporting.
#: A handful could be a stray write; a region that is substantially populated
#: is not.
MIN_NONZERO = 16


def filesystem_kind(image: bytes) -> str:
    """FAT, ext or NTFS, decided by structure rather than by file extension.

    NTFS is checked before FAT because an NTFS boot sector also ends in 0x55AA
    -- it has to, to be bootable. Testing the FAT signature first would call
    every NTFS volume a FAT one and then read its BPB fields at the wrong
    offsets, producing a geometry that looks plausible and is nonsense.
    """
    if len(image) >= 512 and image[3:11] == b"NTFS    ":
        return "ntfs"
    if len(image) >= 2048 and image[1024 + 56:1024 + 58] == b"\x53\xef":
        return "ext"
    if len(image) >= 512 and image[510:512] == b"\x55\xaa":
        return "fat"
    return "unknown"


#: Named $DATA attributes NTFS creates for its own metafiles. These are not
#: anomalies and reporting them would give the detector a false-positive rate
#: of 100% on every freshly formatted volume.
NTFS_SYSTEM_STREAMS = {"$Bad", "$SDS", "$SII", "$SDH", "$Info", "$Max", "$Q",
                       "$O", "$R", "$J"}


def alternate_streams(image: bytes) -> List[Dict[str, object]]:
    """Named $DATA attributes that are not NTFS's own metadata."""
    if filesystem_kind(image) != "ntfs":
        return []
    vol = parse_ntfs(image)
    if vol.errors:
        return []
    return [s for s in vol.alternate_streams()
            if s["stream"] not in NTFS_SYSTEM_STREAMS]


def read_stream(image: bytes, record: int, name: str) -> bytes:
    """Read a resident alternate stream's bytes, fixups undone."""
    vol = parse_ntfs(image)
    for attr in vol.attributes(record):
        if attr.is_alternate_stream and attr.name == name and attr.resident:
            return vol.resident_value(record, attr)
    return b""


def slack_regions(image: bytes) -> List[SlackRegion]:
    """Slack regions for either filesystem, in one shape.

    The argument does not change between filesystems -- a file leaves the tail
    of its last allocation unused either way. What changes is the work to find
    it: FAT keeps the first cluster in the directory entry, while ext4 keeps an
    inode number there, the extent tree in the inode, and the blocks in the
    tree. Three indirections against one, and an identical result.
    """
    kind = filesystem_kind(image)
    if kind == "fat":
        return parse_fat(image).slack_regions()
    if kind != "ext":
        return []

    vol = parse_ext(image)
    if vol.errors:
        return []
    out = []
    # Inodes 1-10 are reserved; user files start at 11 and the directory walk
    # is not implemented, so the inode table is scanned directly. That finds
    # slack without needing names, which is what the analysis actually wants.
    for inode in range(11, min(vol.inodes_per_group, 512) + 1):
        try:
            region = vol.slack(inode)
        except Exception:                              # noqa: BLE001
            continue
        if region is not None:
            out.append(SlackRegion(name=f"inode:{inode}", offset=region.offset,
                                   length=region.length,
                                   file_size=region.file_size,
                                   cluster_size=region.block_size))
    return out


def embed(image: bytes, payload: bytes, filename: str = "") -> bytes:
    """Write a payload into the slack of the first file that can hold it."""
    for region in slack_regions(image):
        if filename and region.name.upper() != filename.upper():
            continue
        if region.length >= len(payload):
            return write_slack(image, region, payload)
    raise ValueError(f"no slack region large enough for {len(payload)} bytes")


def extract(image: bytes, nbytes: int = 0, filename: str = "") -> bytes:
    """Read back whatever occupies slack. No key: the geometry is the map."""
    out = b""
    for region in slack_regions(image):
        if filename and region.name.upper() != filename.upper():
            continue
        chunk = read_slack(image, region).rstrip(b"\x00")
        if chunk:
            out += chunk
            if nbytes and len(out) >= nbytes:
                break
    return out[:nbytes] if nbytes else out


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def slack_profile(image: bytes) -> List[Dict[str, object]]:
    """Per file: how much slack it has and how much of it is not zero."""
    out = []
    for region in slack_regions(image):
        content = read_slack(image, region)
        stripped = content.rstrip(b"\x00")
        nonzero = sum(1 for b in content if b)
        out.append({
            "file": region.name,
            "file_size": region.file_size,
            "slack_bytes": region.length,
            "nonzero_bytes": nonzero,
            "occupied_prefix": len(stripped),
            "entropy": round(_entropy(stripped), 3) if stripped else 0.0,
            "offset": region.offset,
            "filesystem": filesystem_kind(image),
        })
    return out


def detect(image: bytes, name: str = "<volume>",
           baseline: Optional[FalsePositiveBaseline] = None,
           payload_bytes: int = 0) -> Report:
    report = Report(carrier=name)
    if filesystem_kind(image) == "unknown":
        return report

    # Alternate data streams first: deterministic, and they yield the payload.
    for stream in alternate_streams(image):
        level = cap_without_baseline(Evidence.E4, baseline)
        payload = (read_stream(image, int(stream["record"]), str(stream["stream"]))
                   if stream["resident"] else None)
        report.add(Finding(
            carrier=name, level=level if payload else Evidence.E3,
            detector="ntfs_alternate_stream",
            claim=(f"file in MFT record {stream['record']} carries a named "
                   f"$DATA attribute '{stream['stream']}' of "
                   f"{stream['bytes']} bytes beside a main stream of "
                   f"{stream['main_stream_bytes']}; a directory listing shows "
                   f"only the main stream's size"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="ntfs-ads" if level >= Evidence.E3 else None,
            payload=payload,
            payload_offset=int(stream["offset"]),
            baseline=baseline,
            detail=dict(stream),
        ))

    for entry in slack_profile(image):
        if entry["nonzero_bytes"] < MIN_NONZERO:
            continue
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = None
        if level >= Evidence.E3:
            payload = extract(image, payload_bytes, filename=str(entry["file"]))
            if payload:
                level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="fat_file_slack",
            claim=(f"{entry['nonzero_bytes']} of {entry['slack_bytes']} slack "
                   f"bytes after '{entry['file']}' are non-zero "
                   f"({entry['entropy']:.1f} bits/byte). Freshly formatted "
                   f"clusters are zero; this is either a payload or the tail of "
                   f"a deleted file that held this cluster before"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm=ALGORITHM if level >= Evidence.E3 else None,
            payload=payload,
            payload_offset=int(entry["offset"]),
            baseline=baseline,
            detail=dict(entry),
        ))
    return report


def build_sample(image: bytes, payload: bytes) -> bytes:
    return embed(image, payload)
