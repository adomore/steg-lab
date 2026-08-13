"""NTFS, far enough to find a stream that no directory listing shows.

An alternate data stream is a second `$DATA` attribute on a file, carrying its
own name and its own bytes. `dir` shows the main stream's size and nothing
else; copying the file to a non-NTFS filesystem drops the stream silently. It
is the cleanest example in this repository of a hiding place created by a
format feature working exactly as designed.

Two structural facts make NTFS different from FAT and ext4, and both matter to
an examiner:

**Small attributes are RESIDENT.** A short stream lives inside the file's MFT
record rather than in a data cluster, so a carve that walks the data area will
not find it and neither will a slack scan.

**MFT records carry FIXUPS.** The last two bytes of every 512-byte sector in a
record are replaced by an update-sequence number, with the real bytes kept in
an array at the top of the record. A resident stream that spans a sector
boundary therefore appears *broken* in a raw image while reading back
perfectly through a driver -- a payload that is byte-exact and not contiguous.
Any tool that searches an image for a known string can miss it for that reason
alone.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional

NTFS_OEM = b"NTFS    "
FILE_MAGIC = b"FILE"
ATTR_DATA = 0x80
ATTR_END = 0xFFFFFFFF


class NtfsError(Exception):
    pass


@dataclass
class Attribute:
    type_id: int
    name: str
    resident: bool
    offset: int          # offset of the attribute record within the image
    length: int
    value_offset: int    # offset of the value, for resident attributes
    value_length: int

    @property
    def is_data(self) -> bool:
        return self.type_id == ATTR_DATA

    @property
    def is_alternate_stream(self) -> bool:
        return self.is_data and self.name != ""


@dataclass
class NtfsVolume:
    data: bytes
    bytes_per_sector: int = 0
    sectors_per_cluster: int = 0
    mft_cluster: int = 0
    record_size: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def mft_offset(self) -> int:
        return self.mft_cluster * self.cluster_size

    def record_offset(self, number: int) -> int:
        return self.mft_offset + number * self.record_size

    def apply_fixups(self, record: bytes) -> bytes:
        """Undo the update-sequence substitution.

        Without this the last two bytes of every sector in the record are the
        update-sequence number rather than the data that belongs there. A
        parser that skips this step reads plausible-looking attribute headers
        with two bytes wrong every 512, which is worse than failing.
        """
        if len(record) < 8 or record[:4] != FILE_MAGIC:
            return record
        usa_offset, usa_count = struct.unpack("<HH", record[4:8])
        if usa_count < 2:
            return record
        out = bytearray(record)
        usn = record[usa_offset:usa_offset + 2]
        for i in range(1, usa_count):
            entry = record[usa_offset + i * 2:usa_offset + i * 2 + 2]
            end = i * self.bytes_per_sector - 2
            if end + 2 <= len(out) and bytes(out[end:end + 2]) == usn:
                out[end:end + 2] = entry
        return bytes(out)

    def attributes(self, number: int) -> List[Attribute]:
        """Attributes of one MFT record."""
        base = self.record_offset(number)
        raw = self.data[base:base + self.record_size]
        if len(raw) < 48 or raw[:4] != FILE_MAGIC:
            raise NtfsError(f"record {number} is not an MFT record")
        fixed = self.apply_fixups(raw)

        first = struct.unpack("<H", fixed[20:22])[0]
        out: List[Attribute] = []
        pos = first
        while pos + 4 <= len(fixed):
            type_id = struct.unpack("<I", fixed[pos:pos + 4])[0]
            if type_id == ATTR_END:
                break
            if pos + 16 > len(fixed):
                break
            length = struct.unpack("<I", fixed[pos + 4:pos + 8])[0]
            if length == 0 or pos + length > len(fixed):
                break
            non_resident = fixed[pos + 8]
            name_len = fixed[pos + 9]
            name_off = struct.unpack("<H", fixed[pos + 10:pos + 12])[0]
            name = (fixed[pos + name_off:pos + name_off + name_len * 2]
                    .decode("utf-16-le", "replace") if name_len else "")

            if non_resident:
                value_off, value_len = 0, 0
            else:
                value_len = struct.unpack("<I", fixed[pos + 16:pos + 20])[0]
                value_off = struct.unpack("<H", fixed[pos + 20:pos + 22])[0]
            out.append(Attribute(type_id=type_id, name=name,
                                 resident=not non_resident,
                                 offset=base + pos, length=length,
                                 value_offset=base + pos + value_off,
                                 value_length=value_len))
            pos += length
        return out

    def resident_value(self, number: int, attr: Attribute) -> bytes:
        """Read a resident attribute's bytes, fixups undone."""
        base = self.record_offset(number)
        fixed = self.apply_fixups(self.data[base:base + self.record_size])
        start = attr.value_offset - base
        return fixed[start:start + attr.value_length]

    def alternate_streams(self, limit: int = 128) -> List[Dict[str, object]]:
        """Every named $DATA attribute in the first `limit` MFT records."""
        out = []
        for number in range(limit):
            try:
                attrs = self.attributes(number)
            except (NtfsError, struct.error):
                continue
            names = [a for a in attrs if a.is_alternate_stream]
            if not names:
                continue
            main = [a for a in attrs if a.is_data and not a.name]
            for attr in names:
                out.append({
                    "record": number,
                    "stream": attr.name,
                    "resident": attr.resident,
                    "bytes": attr.value_length,
                    "offset": attr.value_offset,
                    "main_stream_bytes": main[0].value_length if main else 0,
                })
        return out


def parse_ntfs(data: bytes) -> NtfsVolume:
    """Read an NTFS boot sector. Malformed input yields errors."""
    vol = NtfsVolume(data=data)
    if len(data) < 512:
        vol.errors.append("shorter than one sector")
        return vol
    if data[3:11] != NTFS_OEM:
        vol.errors.append("no 'NTFS    ' OEM identifier")
        return vol

    vol.bytes_per_sector = struct.unpack("<H", data[11:13])[0]
    vol.sectors_per_cluster = data[13]
    vol.mft_cluster = struct.unpack("<Q", data[48:56])[0]
    clusters_per_record = struct.unpack("<b", data[64:65])[0]
    if clusters_per_record < 0:
        vol.record_size = 1 << (-clusters_per_record)
    else:
        vol.record_size = clusters_per_record * vol.bytes_per_sector * vol.sectors_per_cluster
    if vol.record_size == 0:
        vol.errors.append("zero MFT record size")
    return vol
