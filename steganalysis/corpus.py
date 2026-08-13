"""Seeded synthetic cover generation.

The repository stores no binary carriers.  It stores this module plus a
manifest of SHA-256 digests; `corpus/generate.py` reproduces the exact same
bytes on any machine.  That keeps the repo small, sidesteps every image
licensing question, and -- the part that actually matters for the science --
makes "same source" a property you can prove rather than assert.

Synthetic covers are NOT a substitute for real ones.  Real sensor noise is
what statistical detectors key on, and synthetic textures have the wrong
noise model.  Gates G4/G5 therefore run against BOSSbase/ALASKA2 pulled by
reference (see scripts/get-corpora.sh).  Synthetic covers are used where
the question is structural rather than statistical -- which is exactly the
whole A group.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image


@dataclass
class CoverSpec:
    name: str
    seed: int
    width: int
    height: int
    kind: str          # gradient | texture | photo_like | flat | composite
    fmt: str           # "png" | "jpeg"
    quality: int = 90  # JPEG only


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _gradient(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    base = (xs / max(w - 1, 1)) * 180.0 + (ys / max(h - 1, 1)) * 60.0
    img = np.stack([base, base * 0.8 + 30, base * 0.6 + 60], axis=-1)
    img += rng.normal(0, 1.5, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _texture(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    """Band-limited noise: rough enough that LSB planes look plausible."""
    low = rng.normal(0, 1, (max(h // 8, 2), max(w // 8, 2), 3))
    img = np.array(Image.fromarray(
        np.clip(low * 40 + 128, 0, 255).astype(np.uint8)
    ).resize((w, h), Image.BICUBIC), dtype=np.float64)
    img += rng.normal(0, 6, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _photo_like(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    """Smooth regions + edges + grain, i.e. a caricature of a photograph."""
    img = _texture(w, h, rng).astype(np.float64)
    ys, xs = np.mgrid[0:h, 0:w]
    cx, cy = rng.integers(w // 4, 3 * w // 4), rng.integers(h // 4, 3 * h // 4)
    r = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    disc = (r < min(w, h) * 0.22)[..., None]
    img = np.where(disc, img * 0.45 + 150, img)
    for _ in range(4):
        y0 = int(rng.integers(0, h))
        img[y0:y0 + 2, :, :] = np.clip(img[y0:y0 + 2, :, :] * 0.6, 0, 255)
    img += rng.normal(0, 2.5, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _flat(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    val = int(rng.integers(60, 200))
    img = np.full((h, w, 3), val, dtype=np.float64)
    img += rng.normal(0, 0.8, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _composite(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    """Half near-flat, half strongly textured.

    Adaptive embedding needs somewhere cheap and somewhere expensive. The
    other four families are texturally homogeneous, so a cost function cannot
    discriminate on them and adaptivity has nothing to buy -- measured HILL
    cost dynamic range 1.7x to 5.3x, against 96x here. Real photographs sit
    far past even this; see gap G-15.
    """
    img = np.full((h, w, 3), 128.0)
    split = w // 2
    img[:, split:, :] += rng.normal(0, 25, (h, w - split, 3))
    img[:, :split, :] += rng.normal(0, 0.3, (h, split, 3))
    return np.clip(img, 0, 255).astype(np.uint8)


_KINDS = {
    "gradient": _gradient,
    "texture": _texture,
    "photo_like": _photo_like,
    "flat": _flat,
    "composite": _composite,
}


def render(spec: CoverSpec) -> bytes:
    """Deterministically render one cover to encoded bytes."""
    rng = _rng(spec.seed)
    arr = _KINDS[spec.kind](spec.width, spec.height, rng)
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    if spec.fmt == "png":
        # optimize=False keeps zlib output stable across Pillow builds.
        img.save(buf, format="PNG", compress_level=6, optimize=False)
    elif spec.fmt == "jpeg":
        img.save(buf, format="JPEG", quality=spec.quality, subsampling=0)
    else:
        raise ValueError(f"unknown format {spec.fmt}")
    return buf.getvalue()


def default_specs() -> List[CoverSpec]:
    """The P0 working set: 24 covers, 12 PNG and 12 JPEG."""
    specs: List[CoverSpec] = []
    kinds = ["gradient", "texture", "photo_like", "flat"]
    for i in range(12):
        specs.append(CoverSpec(
            name=f"cover_{i:03d}.png", seed=1000 + i,
            width=256, height=192, kind=kinds[i % 4], fmt="png",
        ))
    for i in range(12):
        specs.append(CoverSpec(
            name=f"cover_{i:03d}.jpg", seed=2000 + i,
            width=256, height=192, kind=kinds[i % 4], fmt="jpeg",
            quality=[75, 85, 90, 95][i % 4],
        ))
    return specs


def baseline_specs(n: int = 200, fmt: str = "png", seed0: int = 50_000,
                   kinds: Optional[List[str]] = None) -> List[CoverSpec]:
    """A larger same-source clean set, used to measure false-positive rates.

    "Same source" here means: same generator, same kind rotation, same
    dimensions, same encoder settings.  That is the property a real case
    would have to establish about a camera and its processing chain.
    """
    kinds = list(kinds) if kinds else ["gradient", "texture", "photo_like", "flat"]
    ext = "png" if fmt == "png" else "jpg"
    return [
        CoverSpec(
            name=f"clean_{i:04d}.{ext}", seed=seed0 + i,
            width=256, height=192, kind=kinds[i % len(kinds)], fmt=fmt, quality=90,
        )
        for i in range(n)
    ]


def write_corpus(specs: List[CoverSpec], outdir: Path) -> Dict[str, str]:
    """Render specs into outdir, returning {name: sha256}."""
    outdir.mkdir(parents=True, exist_ok=True)
    digests: Dict[str, str] = {}
    for spec in specs:
        blob = render(spec)
        (outdir / spec.name).write_bytes(blob)
        digests[spec.name] = hashlib.sha256(blob).hexdigest()
    return digests


def write_manifest(specs: List[CoverSpec], digests: Dict[str, str],
                   path: Path, note: Optional[str] = None) -> None:
    manifest = {
        "note": note or ("Regenerate with scripts/regen-corpus.sh. "
                         "Digests pin the exact bytes; a mismatch means the "
                         "renderer or Pillow changed and the gates must be re-run."),
        "specs": [asdict(s) for s in specs],
        "sha256": digests,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def verify_manifest(path: Path, corpus_dir: Path) -> List[str]:
    """Return a list of mismatch descriptions; empty means the corpus is intact."""
    manifest = json.loads(path.read_text())
    problems: List[str] = []
    for name, expected in manifest["sha256"].items():
        f = corpus_dir / name
        if not f.exists():
            problems.append(f"{name}: missing")
            continue
        actual = hashlib.sha256(f.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"{name}: sha256 {actual[:16]}... != {expected[:16]}...")
    return problems
