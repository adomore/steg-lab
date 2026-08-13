#!/usr/bin/env python3
"""Differential test: the Rust triage scanner against the Python reference.

A port that is merely faster is a liability -- it is a second place for bugs
to live. A port that is checked against the original on every file is
something else: two independent implementations agreeing is evidence about
the *format*, not just about one codebase. Gate G1 used pngcheck and djpeg
for exactly this reason; this script extends the same idea inward.

Fields compared per file: container kind, structural end offset, trailing
byte count, the full (type, offset, length) chunk sequence, the CRC-failure
list, the unknown-chunk list, and the JPEG scan statistics.

Run:  python3 scripts/difftest.py [--n 200] [--bench]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from steganalysis import corpus, jpeg as jpeg_mod, png as png_mod  # noqa: E402

CRATE = ROOT / "rust" / "stegscan"


def build_scanner() -> Path | None:
    if shutil.which("cargo") is None:
        return None
    proc = subprocess.run(["cargo", "build", "--release", "--offline", "-q"],
                          cwd=CRATE, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return None
    binary = CRATE / "target" / "release" / "stegscan"
    return binary if binary.exists() else None


def python_view(path: Path) -> Dict:
    data = path.read_bytes()
    view: Dict = {"path": str(path), "size": len(data), "kind": "unknown",
                  "structural_end": None, "trailing_bytes": 0, "chunks": [],
                  "bad_crc": [], "unknown_chunks": [], "scan_bytes": 0,
                  "stuffed_ff": 0, "restart_markers": 0, "errors": []}

    if data.startswith(png_mod.PNG_MAGIC):
        view["kind"] = "png"
        parsed = png_mod.parse_png(data)
        view["structural_end"] = parsed.iend_end
        view["chunks"] = [[c.ctype, c.offset, c.length] for c in parsed.chunks]
        view["bad_crc"] = [c.ctype for c in parsed.bad_crc_chunks()]
        view["unknown_chunks"] = [c.ctype for c in parsed.unknown_chunks()]
        view["errors"] = list(parsed.errors)
    elif data[:3] == b"\xff\xd8\xff":
        view["kind"] = "jpeg"
        parsed = jpeg_mod.parse_jpeg(data)
        view["structural_end"] = parsed.eoi_end
        view["chunks"] = [[s.name, s.offset, s.length] for s in parsed.segments]
        view["scan_bytes"] = sum(s.size for s in parsed.scans)
        view["stuffed_ff"] = sum(s.stuffed_ff for s in parsed.scans)
        view["restart_markers"] = sum(s.restart_markers for s in parsed.scans)
        view["errors"] = list(parsed.errors)
    else:
        view["errors"] = ["unrecognised container"]

    if view["structural_end"] is not None:
        view["trailing_bytes"] = max(0, len(data) - view["structural_end"])
    return view


COMPARED = ["kind", "structural_end", "trailing_bytes", "chunks",
            "bad_crc", "unknown_chunks", "scan_bytes", "stuffed_ff",
            "restart_markers"]


def build_sample_set(workdir: Path, n: int) -> List[Path]:
    """Clean covers plus deliberately anomalous carriers.

    Comparing only well-formed files would test the happy path twice. The
    disagreements worth finding are on malformed input, so the sample set
    includes appended data, private chunks, stale CRCs and truncation.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    half = max(n // 2, 1)
    specs = ([corpus.CoverSpec(f"d_{i:04d}.png", 600_000 + i, 128 + (i % 7) * 8,
                               96 + (i % 5) * 8,
                               ["gradient", "texture", "photo_like", "flat"][i % 4],
                               "png") for i in range(half)]
             + [corpus.CoverSpec(f"d_{i:04d}.jpg", 610_000 + i, 128 + (i % 7) * 8,
                                 96 + (i % 5) * 8,
                                 ["gradient", "texture", "photo_like", "flat"][i % 4],
                                 "jpeg", quality=[70, 85, 95][i % 3])
                for i in range(n - half)])
    corpus.write_corpus(specs, workdir)
    paths.extend(workdir / s.name for s in specs)

    sys.path.insert(0, str(ROOT))
    from labs.common import load_lab
    lab01, lab04, lab06 = (load_lab("01_trailing_data"), load_lab("04_png_chunks"),
                           load_lab("06_jpeg_segments"))

    base_png = corpus.render(corpus.CoverSpec("b.png", 620_001, 128, 96, "texture", "png"))
    base_jpg = corpus.render(corpus.CoverSpec("b.jpg", 620_002, 128, 96, "photo_like",
                                              "jpeg", quality=90))
    anomalies = {
        "anom_trailing.png": lab01.embed(base_png, b"TRAILING" * 8),
        "anom_trailing.jpg": lab01.embed(base_jpg, b"TRAILING" * 8),
        "anom_private.png": lab04.embed(base_png, b"PRIVATE" * 8, variant="private_chunk"),
        "anom_crc.png": lab04.embed(base_png, b"OVERWRITE", variant="stale_crc"),
        "anom_trunc.png": lab04.embed(base_png, b"", variant="height_truncation"),
        "anom_com.jpg": lab06.embed(base_jpg, b"COMMENT" * 8, variant="comment"),
        "anom_appn.jpg": lab06.embed(base_jpg, b"ROGUE" * 8, variant="rogue_appn"),
        "anom_cut.png": base_png[:len(base_png) // 2],
        "anom_cut.jpg": base_jpg[:len(base_jpg) // 2],
        "anom_notimage.bin": b"\x00\x01\x02\x03" * 64,
    }
    for name, blob in anomalies.items():
        p = workdir / name
        p.write_bytes(blob)
        paths.append(p)

    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--bench", action="store_true")
    args = ap.parse_args()

    binary = build_scanner()
    if binary is None:
        print("SKIP: cargo or the stegscan binary is unavailable.")
        print("      Install a Rust toolchain, or run scripts/setup-kali.sh.")
        return 0

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        paths = build_sample_set(work / "s", args.n)

        proc = subprocess.run([str(binary)] + [str(p) for p in paths],
                              capture_output=True, text=True)
        rust_rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        rust_by_path = {r["path"]: r for r in rust_rows}

        mismatches: List[str] = []
        compared = 0
        for p in paths:
            py = python_view(p)
            rs = rust_by_path.get(str(p))
            if rs is None:
                mismatches.append(f"{p.name}: no Rust output")
                continue
            compared += 1
            for field in COMPARED:
                a, b = py[field], rs[field]
                if field == "chunks":
                    a = [list(x) for x in a]
                    b = [list(x) for x in b]
                if a != b:
                    mismatches.append(f"{p.name}: {field}\n      py={a}\n      rs={b}")

        print("=" * 70)
        print("Differential test: Rust stegscan vs Python reference")
        print("=" * 70)
        print(f"files compared : {compared}")
        print(f"fields per file: {len(COMPARED)}")
        print(f"mismatches     : {len(mismatches)}")
        for m in mismatches[:10]:
            print("  " + m)

        if args.bench and not mismatches:
            bench = subprocess.run([str(binary), "--bench"] + [str(p) for p in paths],
                                   capture_output=True, text=True)
            if bench.stdout.strip():
                stats = json.loads(bench.stdout.strip())
                print("-" * 70)
                print(f"rust throughput: {stats['files_per_sec']:.0f} files/s, "
                      f"{stats['mb_per_sec']:.1f} MB/s")

                import time
                t0 = time.perf_counter()
                rounds = 3
                for _ in range(rounds):
                    for p in paths:
                        python_view(p)
                dt = time.perf_counter() - t0
                py_fps = (len(paths) * rounds) / dt
                print(f"python throughput: {py_fps:.0f} files/s")
                print(f"speedup: {stats['files_per_sec'] / py_fps:.1f}x")

        print("=" * 70)
        print("DIFFTEST:", "FAIL" if mismatches else "PASS")
        return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
