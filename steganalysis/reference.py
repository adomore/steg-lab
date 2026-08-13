"""Reference corpora: loading real images that do not live in this repository.

Everything under `steganalysis.corpus` is synthetic and reproducible from a
seed. That was enough for the structural labs and it is demonstrably not
enough for the statistical ones -- gate G4 measured a 33.8% false-positive
rate for the chi-square attack on synthetic covers, and gate G3 measured
HILL cost dynamic ranges under 6x where real photographs span orders of
magnitude.

This module reads a real corpus from wherever the analyst put it. Nothing is
downloaded and nothing is vendored: a 1.6 GB archive has no business in a
git repository, and the licensing is not ours to redistribute.

Reading directly from the zip is supported because it matters at this size.
BOSSbase 1.01 is 1.6 GB compressed and about 2.6 GB unpacked (10,000 files
at 512x512x8 bits), so unpacking costs more disk than the download did.

The camera partition is the reason BOSSbase is worth the trouble. Cover
source mismatch has been the sharpest result in this repository twice --
0% to 25% false positives in T4, P_E 0.140 to 0.487 in T5 -- and both were
demonstrated on synthetic image families. Seven real cameras let the same
experiment run on the thing it is actually about.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

#: Image suffixes the loader will discover. PGM covers BOSSbase; JPEG covers
#: ALASKA2, which is the candidate second acquisition pipeline for gap G-18 --
#: BOSSbase's seven cameras all went through one RAW development script, so a
#: cross-camera shift there isolates the sensor and is mild by construction.
IMAGE_SUFFIXES = (".pgm", ".pgm.gz", ".jpg", ".jpeg", ".tif", ".tiff", ".png")


def decode_image(name: str, blob: bytes) -> np.ndarray:
    """Read a corpus member as an 8-bit array, dispatching on its suffix.

    PGM is parsed here (see read_pgm and why it is not delegated). Everything
    else goes through Pillow and is converted to a single channel: every
    detector in this repository assumes one 8-bit plane, and silently handing
    them three would produce numbers that look fine.
    """
    lower = name.lower()
    if lower.endswith(".pgm"):
        return read_pgm(blob)
    try:
        from PIL import Image
        import io as _io
        return np.array(Image.open(_io.BytesIO(blob)).convert("L"))
    except Exception as exc:                          # noqa: BLE001
        raise CorpusError(f"{name}: cannot decode ({exc})")


#: Published index ranges for BOSSbase 1.01's seven source cameras.
#:
#: SECONDARY SOURCE, structurally checked. These come from secondary sources
#: rather than from the dataset's own documentation, so they are not
#: authoritative -- but they are not obviously wrong either, which an earlier
#: version of this comment claimed. Checked: the seven ranges are contiguous
#: from index 1 with no gaps or overlaps, and they cover 1..10000 exactly
#: (10,000 files). The top range extends to 10212, consistent with having
#: been stated for the larger RAW set rather than for the 1.01 covers.
#:
#: The camera partition is what makes a real cover-source mismatch experiment
#: possible, which is why it is worth carrying an unauthoritative version.
#: `scripts/register-corpus.py` re-checks contiguity against the actual file
#: count. Confirm against the dataset's own README before quoting these in
#: anything evidential.
BOSSBASE_CAMERAS_UNVERIFIED: Dict[str, Tuple[int, int]] = {
    "canon_eos_400d": (1, 1354),
    "canon_eos_40d": (1355, 1415),
    "canon_eos_7d": (1416, 2769),
    "canon_rebel_xsi": (2770, 4811),
    "pentax_k20d": (4812, 6209),
    "nikon_d70": (6210, 7242),
    "leica_m9": (7243, 10212),
}


class CorpusError(Exception):
    pass


# --------------------------------------------------------------------------
# PGM reading
# --------------------------------------------------------------------------

def read_pgm(data: bytes) -> np.ndarray:
    """Parse a binary (P5) or ASCII (P2) PGM from bytes.

    Written out rather than delegated because the failure modes matter here:
    a 16-bit maxval, a comment line in the header, or a stray whitespace
    convention would all be silently mishandled by a lenient reader, and the
    result would be a corpus that looks fine and is not.
    """
    if not data.startswith(b"P5") and not data.startswith(b"P2"):
        raise CorpusError("not a PGM file (expected magic P5 or P2)")
    binary = data.startswith(b"P5")

    # Header: magic, width, height, maxval -- whitespace-separated, with
    # '#' comments legal anywhere up to the end of the maxval token.
    pos = 2
    fields: List[int] = []
    while len(fields) < 3:
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while pos < len(data) and data[pos:pos + 1] not in (b"\n", b"\r"):
                pos += 1
            continue
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        fields.append(int(data[start:pos]))
    width, height, maxval = fields
    pos += 1                       # exactly one whitespace byte after maxval

    if maxval > 255:
        raise CorpusError(f"16-bit PGM (maxval {maxval}) is not supported; "
                          f"the detectors here assume 8-bit samples")

    if binary:
        expected = width * height
        pixels = np.frombuffer(data[pos:pos + expected], dtype=np.uint8)
        if pixels.size != expected:
            raise CorpusError(f"truncated PGM: {pixels.size} of {expected} bytes")
        return pixels.reshape(height, width)

    values = np.array(data[pos:].split(), dtype=np.int64)[:width * height]
    return values.reshape(height, width).astype(np.uint8)


# --------------------------------------------------------------------------
# Corpus discovery
# --------------------------------------------------------------------------

@dataclass
class ReferenceCorpus:
    """A real corpus on disk, as a directory or a zip archive."""

    name: str
    source: Path
    members: List[str] = field(default_factory=list)
    is_zip: bool = False

    def __len__(self) -> int:
        return len(self.members)

    def read(self, member: str) -> np.ndarray:
        blob = (zipfile.ZipFile(self.source).read(member) if self.is_zip
                else (self.source / member).read_bytes())
        return decode_image(member, blob)

    def index_of(self, member: str) -> Optional[int]:
        """BOSSbase names files 1.pgm .. 10000.pgm; the number is provenance."""
        stem = Path(member).stem
        return int(stem) if stem.isdigit() else None

    def sample(self, n: int, seed: int = 0,
               members: Optional[Sequence[str]] = None) -> List[np.ndarray]:
        """Deterministically sample n images.

        Deterministic because a baseline has to be reproducible: a
        false-positive rate measured on a set nobody can reconstruct is not
        a baseline, it is an anecdote.
        """
        pool = list(members) if members is not None else self.members
        if not pool:
            raise CorpusError(f"corpus '{self.name}' is empty")
        rng = np.random.default_rng(seed)
        picks = rng.permutation(len(pool))[:min(n, len(pool))]
        return [self.read(pool[i]) for i in picks]

    def camera_members(self, camera: str,
                       partition: Optional[Dict[str, Tuple[int, int]]] = None
                       ) -> List[str]:
        part = partition or BOSSBASE_CAMERAS_UNVERIFIED
        if camera not in part:
            raise CorpusError(f"unknown camera '{camera}'; known: {sorted(part)}")
        lo, hi = part[camera]
        out = []
        for m in self.members:
            idx = self.index_of(m)
            if idx is not None and lo <= idx <= hi:
                out.append(m)
        return out


def discover(source: Path, name: str = "") -> ReferenceCorpus:
    """Find PGM images under a directory or inside a zip archive."""
    source = Path(source)
    if not source.exists():
        raise CorpusError(f"{source} does not exist")

    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            members = sorted(
                (i.filename for i in zf.infolist()
                 if not i.is_dir()
                 and i.filename.lower().endswith(IMAGE_SUFFIXES)),
                key=lambda m: (len(Path(m).stem), Path(m).stem))
        return ReferenceCorpus(name or source.stem, source, members, is_zip=True)

    members = sorted((str(p.relative_to(source)) for p in source.rglob("*")
                      if p.is_file() and p.name.lower().endswith(IMAGE_SUFFIXES)),
                     key=lambda m: (len(Path(m).stem), Path(m).stem))
    return ReferenceCorpus(name or source.name, source, members, is_zip=False)


#: Named processing chains. G-18's substance is that BOSSbase's seven cameras
#: all went through ONE RAW development script, so a cross-camera shift there
#: isolates the sensor and is mild by construction (P_E 0.125 to 0.160). A
#: second *acquisition* pipeline would need a second dataset; a second
#: *processing* pipeline can be applied to the sensor data already in hand, and
#: that is the shift that actually turns up in casework -- evidence arrives
#: resized, re-encoded and platform-transcoded.
#:
#: Each entry takes an 8-bit array and returns one of the same shape.
def _pipe_native(img: "np.ndarray") -> "np.ndarray":
    return img


def _pipe_box_half(img: "np.ndarray") -> "np.ndarray":
    from PIL import Image
    h, w = img.shape
    small = Image.fromarray(img).resize((w // 2, h // 2), Image.BOX)
    return np.array(small.resize((w, h), Image.BILINEAR))


def _pipe_lanczos_half(img: "np.ndarray") -> "np.ndarray":
    from PIL import Image
    h, w = img.shape
    small = Image.fromarray(img).resize((w // 2, h // 2), Image.LANCZOS)
    return np.array(small.resize((w, h), Image.LANCZOS))


def _pipe_jpeg95(img: "np.ndarray") -> "np.ndarray":
    import io as _io
    from PIL import Image
    buf = _io.BytesIO()
    Image.fromarray(img, mode="L").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return np.array(Image.open(buf).convert("L"))


def _pipe_sharpen(img: "np.ndarray") -> "np.ndarray":
    from scipy import ndimage
    blurred = ndimage.gaussian_filter(img.astype(np.float64), 1.0)
    return np.clip(img.astype(np.float64) + 0.6 * (img - blurred), 0, 255
                   ).astype(np.uint8)


PIPELINES = {
    "native": _pipe_native,
    "box_half": _pipe_box_half,
    "lanczos_half": _pipe_lanczos_half,
    "jpeg95": _pipe_jpeg95,
    "sharpen": _pipe_sharpen,
}


def apply_pipeline(images, name: str):
    """Push a set of covers through a named processing chain."""
    if name not in PIPELINES:
        raise CorpusError(f"unknown pipeline '{name}'; known: {sorted(PIPELINES)}")
    fn = PIPELINES[name]
    return [fn(np.asarray(img)) for img in images]


#: A second ACQUISITION chain, as against the second PROCESSING chain that
#: PIPELINES provides. Gap G-18's substance is that BOSSbase's seven cameras
#: all went through one RAW development script, so a cross-camera shift there
#: isolates the sensor. These photographs did not: they come from different
#: decades, sensors, scanners and publication paths, and they ship with
#: scikit-image so no download is required.
#:
#: Seven usable 256px crops is a small sample and the figure it produces is
#: correspondingly coarse. It is not a replacement for ALASKA2; it is the
#: difference between having no second acquisition source and having one.
SECOND_SOURCE_NAMES = ("camera", "coffee", "chelsea", "moon", "astronaut",
                       "rocket", "cat", "page")


def second_source(side: int = 256) -> List["np.ndarray"]:
    """Real photographs from acquisition chains unrelated to BOSSbase."""
    try:
        import skimage.data as sk
    except ImportError as exc:
        raise CorpusError(f"scikit-image is required for the second source: {exc}")

    out = []
    for name in SECOND_SOURCE_NAMES:
        arr = np.asarray(getattr(sk, name)())
        if arr.ndim == 3:
            arr = np.round(0.299 * arr[..., 0] + 0.587 * arr[..., 1]
                           + 0.114 * arr[..., 2]).astype(np.uint8)
        h, w = arr.shape[:2]
        if h < side or w < side:
            continue
        out.append(arr[(h - side) // 2:(h - side) // 2 + side,
                       (w - side) // 2:(w - side) // 2 + side])
    if not out:
        raise CorpusError(f"no scikit-image sample is at least {side}px square")
    return out


def default_root() -> Path:
    return Path(__file__).resolve().parents[1] / "corpus" / "reference"


def load_registered(root: Optional[Path] = None) -> Optional[ReferenceCorpus]:
    """Reopen whatever `scripts/register-corpus.py` last registered.

    Registration is the authoritative step. An earlier version had the gates
    re-discover the corpus themselves by looking for a filename containing
    "boss", which meant a corpus registered under any other name was invisible
    to them -- the registration succeeded, reported USABLE, and the gates then
    said no corpus was registered. Reading the index the registration wrote
    removes the second opinion.
    """
    root = Path(root) if root else default_root()
    index = root / "index.json"
    if not index.exists():
        return None
    try:
        record = json.loads(index.read_text())
        source = Path(record["source"])
    except (json.JSONDecodeError, KeyError, OSError):
        return None
    if not source.exists():
        return None
    try:
        corpus = discover(source, name=record.get("name", source.stem))
    except CorpusError:
        return None
    return corpus if corpus.members else None


def find_bossbase(root: Optional[Path] = None) -> Optional[ReferenceCorpus]:
    """Locate BOSSbase under corpus/reference/, unpacked or still zipped."""
    root = Path(root) if root else default_root()
    if not root.exists():
        return None

    registered = load_registered(root)
    if registered is not None:
        return registered

    for candidate in sorted(root.iterdir()):
        lower = candidate.name.lower()
        if "boss" not in lower:
            continue
        try:
            corpus = discover(candidate, name="bossbase")
        except CorpusError:
            continue
        if corpus.members:
            return corpus

    try:
        corpus = discover(root, name="bossbase")
    except CorpusError:
        return None
    return corpus if corpus.members else None


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

def verify(corpus: ReferenceCorpus, check: int = 24) -> Dict:
    """Sanity-check a corpus and report what is actually there.

    Reads a sample rather than all 10,000 files: the point is to catch a
    wrong dataset, a partial unzip or a 16-bit variant, and a couple of dozen
    images settle all three.
    """
    problems: List[str] = []
    shapes: Dict[Tuple[int, int], int] = {}
    digests: List[str] = []

    sample = corpus.members[:: max(len(corpus) // check, 1)][:check]
    for member in sample:
        try:
            arr = corpus.read(member)
        except Exception as exc:
            problems.append(f"{member}: {exc}")
            continue
        shapes[arr.shape] = shapes.get(arr.shape, 0) + 1
        if corpus.is_zip:
            with zipfile.ZipFile(corpus.source) as zf:
                digests.append(hashlib.sha256(zf.read(member)).hexdigest())
        else:
            digests.append(
                hashlib.sha256((corpus.source / member).read_bytes()).hexdigest())

    # Is this actually photographic content? Every spatial detector here
    # assumes strong correlation between adjacent pixels; natural images sit
    # above 0.9 lag-1 correlation, noise sits near 0. This check exists
    # because a synthetic stand-in built to validate the loader was Gaussian
    # noise, ran cleanly through both gates, and produced numbers that looked
    # like results and were meaningless. A corpus that loads is not a corpus
    # that means anything.
    correlations: List[float] = []
    for member in sample[:8]:
        try:
            arr = corpus.read(member).astype(np.float64)
        except Exception:
            continue
        a, b = arr[:, :-1].reshape(-1), arr[:, 1:].reshape(-1)
        if a.std() > 1e-9 and b.std() > 1e-9:
            correlations.append(float(np.corrcoef(a, b)[0, 1]))
    mean_corr = float(np.mean(correlations)) if correlations else float("nan")
    photographic = bool(mean_corr > 0.80)
    if correlations and not photographic:
        problems.append(
            f"lag-1 horizontal correlation is {mean_corr:.3f}; natural images "
            f"exceed 0.90. This content is not photographic, so statistical "
            f"detector results from it will not mean anything. Check that the "
            f"path points at the real dataset")

    indices = [i for i in (corpus.index_of(m) for m in corpus.members) if i is not None]
    camera_counts = {}
    if indices:
        for cam, (lo, hi) in BOSSBASE_CAMERAS_UNVERIFIED.items():
            camera_counts[cam] = sum(1 for i in indices if lo <= i <= hi)

    # Structural check on the partition: contiguous from 1, no gaps, no
    # overlaps, and every indexed file accounted for. This does not make the
    # ranges authoritative -- only self-consistent.
    partition_ok = True
    ranges = sorted(BOSSBASE_CAMERAS_UNVERIFIED.values())
    if ranges[0][0] != 1 or any(ranges[i][1] + 1 != ranges[i + 1][0]
                                for i in range(len(ranges) - 1)):
        partition_ok = False
        problems.append("camera ranges are not a contiguous partition from index 1")
    if indices and sum(camera_counts.values()) != len(indices):
        partition_ok = False
        problems.append(
            f"camera ranges account for {sum(camera_counts.values())} of "
            f"{len(indices)} indexed files")

    return {
        "name": corpus.name,
        "source": str(Path(corpus.source).resolve()),
        "is_zip": corpus.is_zip,
        "files": len(corpus),
        "checked": len(sample),
        "shapes": {f"{h}x{w}": c for (h, w), c in shapes.items()},
        "unique_digests": len(set(digests)),
        "camera_counts": camera_counts,
        "camera_partition_consistent": partition_ok,
        "lag1_correlation": round(mean_corr, 4) if correlations else None,
        "photographic": photographic,
        "problems": problems,
        "usable": (len(corpus) > 0 and photographic
                   and not any("truncated" in p or "not a PGM" in p
                               for p in problems)),
    }


def write_index(corpus: ReferenceCorpus, report: Dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
