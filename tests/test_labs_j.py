"""J-group tests: filesystem slack.

Volumes are built with mkfs.vfat and written with mtools, so the tests skip
cleanly on a machine without them rather than testing this parser against its
own assumptions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402
from steganalysis.fat import parse_fat  # noqa: E402

HAVE_TOOLS = all(shutil.which(t) for t in ("mkfs.vfat", "mcopy", "mdel"))
pytestmark = pytest.mark.skipif(not HAVE_TOOLS,
                                reason="dosfstools/mtools not installed")
ENV = dict(os.environ, MTOOLS_SKIP_CHECK="1")


def build_volume(tmp_path: Path, files, delete=()) -> bytes:
    image = tmp_path / "vol.img"
    subprocess.run(["dd", "if=/dev/zero", f"of={image}", "bs=1M", "count=16"],
                   check=True, capture_output=True)
    subprocess.run(["mkfs.vfat", "-F", "16", "-s", "8", "-n", "STEGLAB",
                    str(image)], check=True, capture_output=True)
    for name, content in files:
        src = tmp_path / name
        src.write_bytes(content)
        subprocess.run(["mcopy", "-i", str(image), str(src), f"::/{name}"],
                       check=True, env=ENV, capture_output=True)
    for name in delete:
        subprocess.run(["mdel", "-i", str(image), f"::/{name}"],
                       check=True, env=ENV, capture_output=True)
    return image.read_bytes()


def test_geometry_and_sizes_match_mtools(tmp_path):
    blob = build_volume(tmp_path, [("A.TXT", b"short\n"),
                                   ("B.BIN", b"x" * 5000)])
    vol = parse_fat(blob)
    assert vol.errors == []
    assert vol.cluster_size == 4096
    sizes = {e.name: e.size for e in vol.root_entries_list() if e.is_file}
    assert sizes == {"A.TXT": 6, "B.BIN": 5000}


def test_exact_cluster_fit_has_no_slack(tmp_path):
    """8192 bytes in 4096-byte clusters leaves nothing over."""
    blob = build_volume(tmp_path, [("C.DAT", b"y" * 8192)])
    assert parse_fat(blob).slack_regions() == []


def test_slack_length_is_the_cluster_remainder(tmp_path):
    blob = build_volume(tmp_path, [("B.BIN", b"x" * 5000)])
    region = parse_fat(blob).slack_regions()[0]
    assert region.length == 4096 - (5000 % 4096)


def test_fresh_volume_has_no_nonzero_slack(tmp_path):
    """mkfs zeroes clusters, which is what makes the baseline strong."""
    lab = load_lab("23_filesystem")
    blob = build_volume(tmp_path, [("A.TXT", b"short\n"),
                                   ("B.BIN", b"x" * 5000)])
    assert all(e["nonzero_bytes"] == 0 for e in lab.slack_profile(blob))
    assert lab.detect(blob, "v", baseline=None).verdict == Evidence.E0


def test_payload_round_trips_and_is_detected(tmp_path):
    lab = load_lab("23_filesystem")
    blob = build_volume(tmp_path, [("A.TXT", b"short\n")])
    data = b"lab23 payload hidden in the tail of a cluster"
    stego = lab.embed(blob, data)
    assert lab.extract(stego, len(data)) == data
    assert lab.detect(stego, "v", baseline=None).verdict >= Evidence.E1


def test_embedding_does_not_disturb_the_file(tmp_path):
    """The file reads back identically; only its unused tail changed."""
    lab = load_lab("23_filesystem")
    original = b"short file content\n"
    blob = build_volume(tmp_path, [("A.TXT", original)])
    stego = lab.embed(blob, b"payload" * 20)
    vol = parse_fat(stego)
    entry = [e for e in vol.root_entries_list() if e.is_file][0]
    start = vol.cluster_offset(entry.first_cluster)
    assert stego[start:start + entry.size] == original
    assert entry.size == len(original)


def test_deleted_file_residue_is_indistinguishable(tmp_path):
    """The twin, asserted rather than described.

    A deliberate payload and a deleted file's tail produce the same finding.
    No statistic here separates them, and the detector says so in its claim
    instead of guessing.
    """
    lab = load_lab("23_filesystem")
    blob = build_volume(tmp_path,
                        [("BIG.DAT", b"CONFIDENTIAL MEMO " * 220)],
                        delete=["BIG.DAT"])
    image = tmp_path / "vol.img"
    src = tmp_path / "NEW.TXT"
    src.write_bytes(b"short\n")
    subprocess.run(["mcopy", "-i", str(image), str(src), "::/NEW.TXT"],
                   check=True, env=ENV, capture_output=True)
    residue_volume = image.read_bytes()

    report = lab.detect(residue_volume, "v", baseline=None)
    assert report.verdict >= Evidence.E1
    assert b"CONFIDENTIAL MEMO" in lab.extract(residue_volume, 200)
    assert "deleted file" in report.findings[0].claim


def test_reaches_e4_with_a_baseline(tmp_path):
    lab = load_lab("23_filesystem")
    blob = build_volume(tmp_path, [("A.TXT", b"short\n")])
    data = b"recovered without a key" * 3
    stego = lab.embed(blob, data)
    baseline = FalsePositiveBaseline("fat_file_slack", 8, 0, 16.0,
                                     "8 freshly formatted volumes")
    report = lab.detect(stego, "v", baseline=baseline, payload_bytes=len(data))
    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == data


def test_capacity_is_enforced(tmp_path):
    lab = load_lab("23_filesystem")
    blob = build_volume(tmp_path, [("A.TXT", b"short\n")])
    with pytest.raises(ValueError, match="no slack region"):
        lab.embed(blob, b"z" * 100_000)


# --------------------------------------------------- ext4 (G-1, second half)

HAVE_EXT = all(shutil.which(t) for t in ("mkfs.ext4", "debugfs"))


def build_ext_volume(tmp_path: Path, files) -> bytes:
    image = tmp_path / "ext.img"
    subprocess.run(["dd", "if=/dev/zero", f"of={image}", "bs=1M", "count=16"],
                   check=True, capture_output=True)
    subprocess.run(["mkfs.ext4", "-q", "-b", "1024", "-F", str(image)],
                   check=True, capture_output=True)
    for name, content in files:
        src = tmp_path / name
        src.write_bytes(content)
        subprocess.run(["debugfs", "-w", "-R", f"write {src} {name}",
                        str(image)], check=True, capture_output=True)
    return image.read_bytes()


@pytest.mark.skipif(not HAVE_EXT, reason="e2fsprogs not installed")
def test_ext_geometry_and_size_match_debugfs(tmp_path):
    from steganalysis.extfs import parse_ext
    blob = build_ext_volume(tmp_path, [("A.TXT", b"hello ext4 slack\n")])
    vol = parse_ext(blob)
    assert vol.errors == []
    assert vol.block_size == 1024

    out = subprocess.run(["debugfs", "-R", "stat A.TXT",
                          str(tmp_path / "ext.img")],
                         capture_output=True, text=True).stdout
    inode = int(out.split("Inode:")[1].split()[0])
    size = int(out.split("Size:")[1].split()[0])
    assert vol.file_size(inode) == size == 17


@pytest.mark.skipif(not HAVE_EXT, reason="e2fsprogs not installed")
def test_ext_slack_offset_lands_in_the_last_extent_block(tmp_path):
    """Cross-checked against debugfs's own extent listing."""
    from steganalysis.extfs import parse_ext
    blob = build_ext_volume(tmp_path, [("B.BIN", b"x" * 3000)])
    vol = parse_ext(blob)
    out = subprocess.run(["debugfs", "-R", "stat B.BIN",
                          str(tmp_path / "ext.img")],
                         capture_output=True, text=True).stdout
    inode = int(out.split("Inode:")[1].split()[0])
    extents = out.split("EXTENTS:")[-1].strip().split("\n")[0]
    last_block = int(extents.split(":")[-1].split("-")[-1])

    region = vol.slack(inode)
    assert region is not None
    assert region.length == 1024 - (3000 % 1024)
    assert region.offset == last_block * 1024 + (3000 % 1024)


@pytest.mark.skipif(not HAVE_EXT, reason="e2fsprogs not installed")
def test_ext_exact_block_fit_has_no_slack(tmp_path):
    from steganalysis.extfs import parse_ext
    blob = build_ext_volume(tmp_path, [("C.DAT", b"y" * 2048)])
    vol = parse_ext(blob)
    out = subprocess.run(["debugfs", "-R", "stat C.DAT",
                          str(tmp_path / "ext.img")],
                         capture_output=True, text=True).stdout
    inode = int(out.split("Inode:")[1].split()[0])
    assert vol.slack(inode) is None


@pytest.mark.skipif(not HAVE_EXT, reason="e2fsprogs not installed")
def test_ext_round_trips_through_the_same_lab_interface(tmp_path):
    """One argument, two filesystems: FAT and ext4 differ only in the lookup."""
    lab = load_lab("23_filesystem")
    blob = build_ext_volume(tmp_path, [("A.TXT", b"short\n")])
    assert lab.filesystem_kind(blob) == "ext"
    assert lab.detect(blob, "v", baseline=None).verdict == Evidence.E0

    data = b"payload recovered from an unmounted ext4 image"
    stego = lab.embed(blob, data)
    assert lab.extract(stego, len(data)) == data
    assert lab.detect(stego, "v", baseline=None).verdict >= Evidence.E1


@pytest.mark.skipif(not HAVE_EXT, reason="e2fsprogs not installed")
def test_unsupported_ext_layouts_are_refused_not_guessed(tmp_path):
    """A slack offset from a misread extent points at somebody else's data.

    An unallocated inode has a zeroed extent header, so the magic check is
    what stops the parser reading twelve bytes of nothing as a block address.
    """
    from steganalysis.extfs import ExtError, parse_ext
    blob = build_ext_volume(tmp_path, [("A.TXT", b"short\n")])
    vol = parse_ext(blob)
    with pytest.raises(ExtError, match="extent|inline"):
        vol.extents(400)        # exists in the table, never allocated


# --------------------------------------------- NTFS alternate data streams

HAVE_NTFS = all(shutil.which(t) for t in ("mkntfs", "ntfscp", "ntfscat"))


def build_ntfs_volume(tmp_path: Path, streams=()) -> bytes:
    image = tmp_path / "ntfs.img"
    subprocess.run(["dd", "if=/dev/zero", f"of={image}", "bs=1M", "count=16"],
                   check=True, capture_output=True)
    subprocess.run(["mkntfs", "-F", "-q", str(image)],
                   check=True, capture_output=True)
    main = tmp_path / "v.txt"
    main.write_bytes(b"visible content\n")
    subprocess.run(["ntfscp", str(image), str(main), "V.TXT"],
                   check=True, capture_output=True)
    for name, content in streams:
        src = tmp_path / f"{name}.bin"
        src.write_bytes(content)
        subprocess.run(["ntfscp", "-N", name, str(image), str(src), "V.TXT"],
                       check=True, capture_output=True)
    return image.read_bytes()


@pytest.mark.skipif(not HAVE_NTFS, reason="ntfs-3g not installed")
def test_ntfs_is_recognised_before_fat(tmp_path):
    """An NTFS boot sector also ends in 0x55AA, because it has to boot."""
    lab = load_lab("23_filesystem")
    blob = build_ntfs_volume(tmp_path)
    assert blob[510:512] == b"\x55\xaa"
    assert lab.filesystem_kind(blob) == "ntfs"


@pytest.mark.skipif(not HAVE_NTFS, reason="ntfs-3g not installed")
def test_stream_bytes_match_ntfscat(tmp_path):
    """Cross-validated against ntfs-3g's own reader."""
    lab = load_lab("23_filesystem")
    payload = bytes((i * 7 + 13) % 251 for i in range(480))
    blob = build_ntfs_volume(tmp_path, [("nonrep", payload)])
    streams = lab.alternate_streams(blob)
    assert [s["stream"] for s in streams] == ["nonrep"]

    mine = lab.read_stream(blob, int(streams[0]["record"]), "nonrep")
    reference = subprocess.run(
        ["ntfscat", "-n", "nonrep", str(tmp_path / "ntfs.img"), "V.TXT"],
        capture_output=True).stdout
    assert mine == reference == payload


@pytest.mark.skipif(not HAVE_NTFS, reason="ntfs-3g not installed")
def test_fixups_are_undone(tmp_path):
    """The payload reads back exactly and is NOT contiguous in the image.

    NTFS replaces the last two bytes of every 512-byte sector in an MFT record
    with an update-sequence number, keeping the originals in an array at the
    top of the record. A resident stream spanning a sector boundary therefore
    looks broken in a raw image while reading back perfectly -- a string search
    over the image can miss a payload that is plainly there.
    """
    lab = load_lab("23_filesystem")
    payload = bytes((i * 7 + 13) % 251 for i in range(480))
    blob = build_ntfs_volume(tmp_path, [("nonrep", payload)])
    streams = lab.alternate_streams(blob)
    assert lab.read_stream(blob, int(streams[0]["record"]), "nonrep") == payload
    assert blob.find(payload) == -1, "expected a fixup to break contiguity"


@pytest.mark.skipif(not HAVE_NTFS, reason="ntfs-3g not installed")
def test_system_streams_are_not_reported(tmp_path):
    """NTFS metafiles use named streams; reporting them is a 100% FPR."""
    lab = load_lab("23_filesystem")
    from steganalysis.ntfs import parse_ntfs
    blob = build_ntfs_volume(tmp_path)
    assert any(s["stream"] in lab.NTFS_SYSTEM_STREAMS
               for s in parse_ntfs(blob).alternate_streams())
    assert lab.alternate_streams(blob) == []
    assert lab.detect(blob, "v", baseline=None).verdict == Evidence.E0


@pytest.mark.skipif(not HAVE_NTFS, reason="ntfs-3g not installed")
def test_ads_reaches_e4_with_a_baseline(tmp_path):
    lab = load_lab("23_filesystem")
    data = b"HIDDEN-IN-ADS payload\n"
    blob = build_ntfs_volume(tmp_path, [("secret", data)])
    baseline = FalsePositiveBaseline("ntfs_alternate_stream", 8, 0, 0.0,
                                     "8 freshly formatted NTFS volumes")
    report = lab.detect(blob, "v", baseline=baseline)
    assert report.verdict == Evidence.E4
    assert any(f.payload == data for f in report.findings)


@pytest.mark.skipif(not HAVE_NTFS, reason="ntfs-3g not installed")
def test_main_stream_size_hides_the_ads(tmp_path):
    """The listing shows the main stream only; that is the whole trick.

    A 2,000-byte stream does not fit in the 1,024-byte MFT record, so NTFS
    stores it NON-RESIDENT in data clusters and the record keeps only a run
    list. The detector still finds it -- a named $DATA attribute is a named
    $DATA attribute -- but the byte count is not in the record, so it reports
    zero and cannot hand over the payload. That is the honest ceiling: E3 for
    a non-resident stream against E4 for a resident one.
    """
    lab = load_lab("23_filesystem")
    small = lab.alternate_streams(build_ntfs_volume(tmp_path, [("s", b"Z" * 200)]))[0]
    assert small["resident"] and small["bytes"] == 200
    assert small["main_stream_bytes"] == 16

    big = lab.alternate_streams(build_ntfs_volume(tmp_path, [("big", b"Z" * 2000)]))[0]
    assert big["stream"] == "big"
    assert not big["resident"], "2000 bytes should not fit in a 1024-byte record"
