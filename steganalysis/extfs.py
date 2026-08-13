"""ext4 parsing, far enough to find where a file stops and its block does not.

The slack argument from lab 23 is filesystem-independent: a file of N bytes in
a filesystem with B-byte blocks leaves `B - (N mod B)` bytes inside its last
block. What changes between filesystems is how much work it takes to find that
block, and ext4 is a useful contrast with FAT precisely because it is harder.

FAT keeps a file's first cluster in its directory entry and the rest in a
table. ext4 keeps almost nothing in the directory: the entry holds an inode
number, the inode holds an extent tree, and the tree holds the blocks. Three
indirections instead of one, and the payoff for an examiner is the same either
way -- an offset into the volume that no file-level tool will ever read.

Only what lab 23 needs is implemented: superblock geometry, the group
descriptor table, one inode, and a depth-0 extent tree. Deeper trees, inline
data and the classic indirect-block layout are rejected explicitly rather than
guessed at, because a slack offset computed from a misread extent points at
somebody else's data.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional

EXT4_MAGIC = 0xEF53
INCOMPAT_EXTENTS = 0x0040
INODE_FLAG_EXTENTS = 0x00080000
INODE_FLAG_INLINE = 0x10000000
EXTENT_MAGIC = 0xF30A


class ExtError(Exception):
    pass


@dataclass
class ExtSlack:
    inode: int
    offset: int
    length: int
    file_size: int
    block_size: int

    @property
    def end(self) -> int:
        return self.offset + self.length


@dataclass
class ExtVolume:
    data: bytes
    block_size: int = 0
    inode_size: int = 0
    inodes_per_group: int = 0
    blocks_per_group: int = 0
    first_data_block: int = 0
    desc_size: int = 0
    incompat: int = 0
    errors: List[str] = field(default_factory=list)

    def group_descriptor(self, group: int) -> bytes:
        table_block = self.first_data_block + 1
        base = table_block * self.block_size + group * self.desc_size
        return self.data[base:base + self.desc_size]

    def inode_table_block(self, group: int) -> int:
        desc = self.group_descriptor(group)
        lo = struct.unpack("<I", desc[8:12])[0]
        hi = struct.unpack("<I", desc[40:44])[0] if len(desc) >= 44 else 0
        return lo | (hi << 32)

    def inode_bytes(self, inode: int) -> bytes:
        group, index = divmod(inode - 1, self.inodes_per_group)
        base = self.inode_table_block(group) * self.block_size
        off = base + index * self.inode_size
        return self.data[off:off + self.inode_size]

    def extents(self, inode: int) -> List[tuple]:
        """(logical_block, physical_block, count) for a depth-0 extent tree."""
        raw = self.inode_bytes(inode)
        flags = struct.unpack("<I", raw[32:36])[0]
        if flags & INODE_FLAG_INLINE:
            raise ExtError(f"inode {inode} stores its data inline; no block, "
                           f"so no slack")
        if not (flags & INODE_FLAG_EXTENTS):
            raise ExtError(f"inode {inode} does not use extents; the indirect "
                           f"block layout is not implemented")

        body = raw[40:100]
        magic, entries, _maxi, depth, _gen = struct.unpack("<HHHHI", body[:12])
        if magic != EXTENT_MAGIC:
            raise ExtError(f"inode {inode} has no extent header")
        if depth != 0:
            raise ExtError(f"inode {inode} has a depth-{depth} extent tree; "
                           f"only depth 0 is implemented")
        out = []
        for i in range(entries):
            chunk = body[12 + i * 12:24 + i * 12]
            logical, count, start_hi, start_lo = struct.unpack("<IHHI", chunk)
            out.append((logical, (start_hi << 32) | start_lo, count))
        return out

    def file_size(self, inode: int) -> int:
        raw = self.inode_bytes(inode)
        lo = struct.unpack("<I", raw[4:8])[0]
        hi = struct.unpack("<I", raw[108:112])[0] if len(raw) >= 112 else 0
        return lo | (hi << 32)

    def slack(self, inode: int) -> Optional[ExtSlack]:
        size = self.file_size(inode)
        if size == 0:
            return None
        used = size % self.block_size
        if used == 0:
            return None
        chunks = self.extents(inode)
        if not chunks:
            return None
        last_logical = (size - 1) // self.block_size
        for logical, physical, count in chunks:
            if logical <= last_logical < logical + count:
                block = physical + (last_logical - logical)
                return ExtSlack(inode=inode,
                                offset=block * self.block_size + used,
                                length=self.block_size - used,
                                file_size=size, block_size=self.block_size)
        return None


def parse_ext(data: bytes) -> ExtVolume:
    """Read an ext2/3/4 superblock. Malformed input yields errors."""
    vol = ExtVolume(data=data)
    if len(data) < 2048:
        vol.errors.append("shorter than a superblock")
        return vol
    sb = data[1024:2048]
    if struct.unpack("<H", sb[56:58])[0] != EXT4_MAGIC:
        vol.errors.append("no 0xEF53 superblock magic")
        return vol

    log_block = struct.unpack("<I", sb[24:28])[0]
    vol.block_size = 1024 << log_block
    vol.blocks_per_group = struct.unpack("<I", sb[32:36])[0]
    vol.inodes_per_group = struct.unpack("<I", sb[40:44])[0]
    vol.first_data_block = struct.unpack("<I", sb[20:24])[0]
    vol.inode_size = struct.unpack("<H", sb[88:90])[0] or 128
    vol.incompat = struct.unpack("<I", sb[96:100])[0]
    desc = struct.unpack("<H", sb[254:256])[0]
    vol.desc_size = desc if (vol.incompat & 0x0080) and desc else 32

    if not (vol.incompat & INCOMPAT_EXTENTS):
        vol.errors.append("volume does not use extents (ext2/ext3 layout)")
    return vol
