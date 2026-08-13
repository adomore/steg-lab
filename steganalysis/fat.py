"""FAT filesystem parsing, and the space a file is given but does not use.

A filesystem hands out storage in clusters. A file of N bytes in a filesystem
with C-byte clusters occupies ceil(N/C) clusters and leaves C - (N mod C) bytes
inside the last one that belong to the file's allocation and hold none of its
content. That region is **file slack**, and it is invisible to every tool that
reads files rather than volumes -- which is most of them.

This is a different kind of hiding place from every carrier before it. A PNG
chunk or a JPEG segment is part of a file, so copying the file carries the
payload along. Slack is a property of the *volume*: copy the file out and the
payload stays behind; defragment the volume and it moves or vanishes. The
payload does not travel with the thing it is hidden in.

FAT is implemented rather than ext4 or NTFS for a reason that is about honesty,
not simplicity. A FAT image can be created, written and verified end to end
inside this repository -- `mkfs.vfat` builds it, `mcopy` writes into it,
`fsck.vfat` and `mdir` check the result -- so every number here is measured
against independent tools. ext4 slack and NTFS alternate data streams need a
mounted volume and privileges this environment does not have, and a lab that
could not verify itself would be worse than none. They stay recorded as gaps.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class FatError(Exception):
    pass


@dataclass
class DirEntry:
    name: str
    attr: int
    first_cluster: int
    size: int
    entry_offset: int

    @property
    def is_volume_label(self) -> bool:
        return bool(self.attr & 0x08)

    @property
    def is_directory(self) -> bool:
        return bool(self.attr & 0x10)

    @property
    def is_file(self) -> bool:
        return not (self.is_volume_label or self.is_directory)


@dataclass
class SlackRegion:
    """The unused tail of a file's last cluster."""

    name: str
    offset: int
    length: int
    file_size: int
    cluster_size: int

    @property
    def end(self) -> int:
        return self.offset + self.length


@dataclass
class FatVolume:
    data: bytes
    bytes_per_sector: int = 0
    sectors_per_cluster: int = 0
    reserved_sectors: int = 0
    fat_count: int = 0
    root_entries: int = 0
    sectors_per_fat: int = 0
    total_sectors: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def root_offset(self) -> int:
        return ((self.reserved_sectors + self.fat_count * self.sectors_per_fat)
                * self.bytes_per_sector)

    @property
    def data_offset(self) -> int:
        return self.root_offset + self.root_entries * 32

    def cluster_offset(self, cluster: int) -> int:
        return self.data_offset + (cluster - 2) * self.cluster_size

    def fat_entry(self, cluster: int) -> int:
        """FAT16 only; FAT12's packed 12-bit entries are not needed here."""
        base = self.reserved_sectors * self.bytes_per_sector
        pos = base + cluster * 2
        if pos + 2 > len(self.data):
            return 0xFFFF
        return struct.unpack("<H", self.data[pos:pos + 2])[0]

    def chain(self, first: int, limit: int = 1 << 20) -> List[int]:
        out = []
        cluster = first
        while 2 <= cluster < 0xFFF8 and len(out) < limit:
            out.append(cluster)
            cluster = self.fat_entry(cluster)
        return out

    def root_entries_list(self) -> List[DirEntry]:
        out = []
        for i in range(self.root_entries):
            off = self.root_offset + i * 32
            raw = self.data[off:off + 32]
            if len(raw) < 32 or raw[0] == 0x00:
                break
            if raw[0] == 0xE5:                      # deleted
                continue
            if raw[11] == 0x0F:                     # long-filename fragment
                continue
            name = raw[:8].decode("latin-1").rstrip()
            ext = raw[8:11].decode("latin-1").rstrip()
            out.append(DirEntry(
                name=f"{name}.{ext}" if ext else name,
                attr=raw[11],
                first_cluster=struct.unpack("<H", raw[26:28])[0],
                size=struct.unpack("<I", raw[28:32])[0],
                entry_offset=off))
        return out

    def slack_regions(self) -> List[SlackRegion]:
        """One region per file: the tail of its final cluster."""
        out = []
        for entry in self.root_entries_list():
            if not entry.is_file or entry.size == 0:
                continue
            chain = self.chain(entry.first_cluster)
            if not chain:
                continue
            used_in_last = entry.size % self.cluster_size
            if used_in_last == 0:
                continue                            # exact fit, no slack
            offset = self.cluster_offset(chain[-1]) + used_in_last
            out.append(SlackRegion(name=entry.name, offset=offset,
                                   length=self.cluster_size - used_in_last,
                                   file_size=entry.size,
                                   cluster_size=self.cluster_size))
        return out


def parse_fat(data: bytes) -> FatVolume:
    """Read a FAT16 boot sector. Malformed input yields errors, not exceptions."""
    vol = FatVolume(data=data)
    if len(data) < 512:
        vol.errors.append("shorter than one sector")
        return vol
    if data[510:512] != b"\x55\xaa":
        vol.errors.append("no 0x55AA boot signature")
        return vol

    vol.bytes_per_sector = struct.unpack("<H", data[11:13])[0]
    vol.sectors_per_cluster = data[13]
    vol.reserved_sectors = struct.unpack("<H", data[14:16])[0]
    vol.fat_count = data[16]
    vol.root_entries = struct.unpack("<H", data[17:19])[0]
    small = struct.unpack("<H", data[19:21])[0]
    vol.sectors_per_fat = struct.unpack("<H", data[22:24])[0]
    vol.total_sectors = small or struct.unpack("<I", data[32:36])[0]

    if vol.bytes_per_sector not in (512, 1024, 2048, 4096):
        vol.errors.append(f"implausible sector size {vol.bytes_per_sector}")
    if vol.sectors_per_cluster == 0:
        vol.errors.append("zero sectors per cluster")
    if vol.root_entries == 0:
        vol.errors.append("no fixed root directory (FAT32 is not supported)")
    return vol


def write_slack(data: bytes, region: SlackRegion, payload: bytes) -> bytes:
    """Place bytes in a slack region, padding the rest with zeros."""
    if len(payload) > region.length:
        raise FatError(f"payload of {len(payload)} exceeds {region.length} "
                       f"bytes of slack in {region.name}")
    out = bytearray(data)
    out[region.offset:region.end] = payload + bytes(region.length - len(payload))
    return bytes(out)


def read_slack(data: bytes, region: SlackRegion) -> bytes:
    return data[region.offset:region.end]
