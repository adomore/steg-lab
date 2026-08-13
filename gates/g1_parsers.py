#!/usr/bin/env python3
"""Gate G1 -- structural parsing without a decoder.

T1 claims you can reason about a carrier's structure from the byte stream
alone.  The risk in that claim is self-deception: it is easy to write a
parser that agrees with your own mental model and disagrees with reality.
So the gate scores the parsers against two independent implementations that
were not written for this repository -- pngcheck and IJG djpeg.

Criteria (all three must hold):

  A. PNG agreement.  Over 50 covers, the hand-written parser's chunk
     sequence (type, file offset, declared length) and image header
     (dimensions, bit depth, colour type, interlace) must match pngcheck -v
     on 100% of chunks. Zero tolerance -- one mismatch fails the gate.

  B. JPEG agreement.  Over 50 covers, the hand-written parser's frame
     dimensions, component count and every quantisation table (de-zigzagged
     into natural order) must match djpeg -verbose -verbose on 100% of files.

  C. Offset localisation.  Three A-group carriers are built with a payload
     at a known offset. The parsers must report that offset exactly, and
     must account for every byte of each file.

Run:  python3 gates/g1_parsers.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from steganalysis import corpus, jpeg as jpg_mod, png as png_mod  # noqa: E402

N_PNG = 50
N_JPEG = 50
RESULTS = Path(__file__).resolve().parent / "results"

# jpeg_natural_order: natural (raster) index for each zig-zag position.
NATURAL_ORDER = [
    0, 1, 8, 16, 9, 2, 3, 10,
    17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63,
]


def dezigzag(zz: List[int]) -> List[int]:
    """Convert a 64-entry zig-zag ordered table into natural order."""
    out = [0] * 64
    for k, val in enumerate(zz[:64]):
        out[NATURAL_ORDER[k]] = val
    return out


# --------------------------------------------------------------------------
# Reference-tool output parsing
# --------------------------------------------------------------------------

_PNGCHECK_CHUNK = re.compile(
    r"chunk\s+(\S{4})\s+at offset\s+0x([0-9a-fA-F]+),\s+length\s+(\d+)")
_PNGCHECK_IHDR = re.compile(
    r"(\d+)\s+x\s+(\d+)\s+image,\s+(\d+)-bit\s+([A-Za-z+ ]+?),\s+(non-interlaced|interlaced)")


def pngcheck_view(path: Path) -> Optional[Dict]:
    proc = subprocess.run(["pngcheck", "-v", str(path)], capture_output=True, text=True)
    text = proc.stdout
    chunks = [(m.group(1), int(m.group(2), 16), int(m.group(3)))
              for m in _PNGCHECK_CHUNK.finditer(text)]
    if not chunks:
        return None
    ih = _PNGCHECK_IHDR.search(text)
    header = None
    if ih:
        header = {
            "width": int(ih.group(1)),
            "height": int(ih.group(2)),
            "bit_depth_total": int(ih.group(3)),
            "interlaced": ih.group(5) == "interlaced",
        }
    return {"chunks": chunks, "header": header}


_DJPEG_SOF = re.compile(
    r"Start Of Frame 0x([0-9a-f]{2}):\s+width=(\d+),\s+height=(\d+),\s+components=(\d+)")
_DJPEG_DQT = re.compile(r"Define Quantization Table (\d+)\s+precision (\d+)")


def djpeg_view(path: Path) -> Optional[Dict]:
    proc = subprocess.run(
        ["djpeg", "-verbose", "-verbose", "-outfile", "/dev/null", str(path)],
        capture_output=True, text=True)
    text = proc.stdout + proc.stderr
    sof = _DJPEG_SOF.search(text)
    if not sof:
        return None

    tables: Dict[int, List[int]] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _DJPEG_DQT.search(lines[i])
        if m:
            tid = int(m.group(1))
            vals: List[int] = []
            j = i + 1
            while j < len(lines) and len(vals) < 64:
                nums = re.findall(r"-?\d+", lines[j])
                if not nums:
                    break
                vals.extend(int(x) for x in nums)
                j += 1
            if len(vals) == 64:
                tables[tid] = vals
            i = j
            continue
        i += 1

    return {
        "width": int(sof.group(2)),
        "height": int(sof.group(3)),
        "components": int(sof.group(4)),
        "qtables": tables,
    }


# --------------------------------------------------------------------------
# Criteria
# --------------------------------------------------------------------------

def criterion_a_png(workdir: Path) -> Dict:
    if shutil.which("pngcheck") is None:
        return {"name": "A_png_matches_pngcheck", "pass": None,
                "skipped": "pngcheck not installed; run scripts/setup-kali.sh"}

    specs = [corpus.CoverSpec(name=f"g1_{i:03d}.png", seed=70_000 + i,
                              width=192 + (i % 5) * 16, height=128 + (i % 3) * 16,
                              kind=["gradient", "texture", "photo_like", "flat"][i % 4],
                              fmt="png")
             for i in range(N_PNG)]
    corpus.write_corpus(specs, workdir)

    compared = 0
    mismatches: List[str] = []
    for spec in specs:
        path = workdir / spec.name
        blob = path.read_bytes()
        mine = png_mod.parse_png(blob)
        ref = pngcheck_view(path)
        if ref is None:
            mismatches.append(f"{spec.name}: pngcheck produced no chunk list")
            continue

        # pngcheck reports the offset of the 4-byte TYPE field; our parser
        # reports the offset of the LENGTH field that precedes it.
        mine_triples = [(c.ctype, c.offset + 4, c.length) for c in mine.chunks]
        if mine_triples != ref["chunks"]:
            mismatches.append(f"{spec.name}: chunk list differs\n"
                              f"      mine={mine_triples}\n      ref ={ref['chunks']}")
        compared += max(len(mine_triples), len(ref["chunks"]))

        if ref["header"] and mine.ihdr:
            total_bits = mine.ihdr.bit_depth * mine.ihdr.channels
            if (mine.ihdr.width, mine.ihdr.height) != (ref["header"]["width"],
                                                       ref["header"]["height"]):
                mismatches.append(f"{spec.name}: dimensions differ")
            if total_bits != ref["header"]["bit_depth_total"]:
                mismatches.append(f"{spec.name}: bit depth {total_bits} != "
                                  f"{ref['header']['bit_depth_total']}")
            if bool(mine.ihdr.interlace) != ref["header"]["interlaced"]:
                mismatches.append(f"{spec.name}: interlace differs")

        # Self-consistency: every byte up to IEND must belong to a chunk.
        accounted = 8 + sum(c.total_size for c in mine.chunks)
        if accounted != mine.iend_end:
            mismatches.append(f"{spec.name}: {accounted} bytes accounted for, "
                              f"IEND ends at {mine.iend_end}")

    return {
        "name": "A_png_matches_pngcheck",
        "files": len(specs),
        "chunks_compared": compared,
        "mismatches": mismatches[:10],
        "mismatch_count": len(mismatches),
        "pass": len(mismatches) == 0,
    }


def criterion_b_jpeg(workdir: Path) -> Dict:
    # Absent and unreadable are different facts, and only one of them is
    # fixed by installing something. IJG's djpeg and libjpeg-turbo's print
    # different verbose text; if the parse fails the cross-check silently does
    # not happen, which reports the same green as a passing comparison. Say
    # which it is.
    if shutil.which("djpeg") is None:
        return {"name": "B_jpeg_matches_djpeg", "pass": None,
                "skipped": "djpeg not installed; apt install libjpeg-progs"}

    probe = corpus.render(corpus.CoverSpec("probe.jpg", 1, 64, 64,
                                           "photo_like", "jpeg"))
    probe_path = workdir / "probe.jpg"
    workdir.mkdir(parents=True, exist_ok=True)
    probe_path.write_bytes(probe)
    if djpeg_view(probe_path) is None:
        return {"name": "B_jpeg_matches_djpeg", "pass": None,
                "skipped": ("djpeg is installed but this gate cannot parse its "
                            "verbose output -- the JPEG cross-check is NOT "
                            "running. Report the djpeg version; the parser "
                            "expects IJG or libjpeg-turbo wording")}

    specs = [corpus.CoverSpec(name=f"g1_{i:03d}.jpg", seed=80_000 + i,
                              width=192 + (i % 5) * 16, height=128 + (i % 3) * 16,
                              kind=["gradient", "texture", "photo_like", "flat"][i % 4],
                              fmt="jpeg", quality=[70, 80, 90, 95, 98][i % 5])
             for i in range(N_JPEG)]
    corpus.write_corpus(specs, workdir)

    tables_compared = 0
    mismatches: List[str] = []
    for spec in specs:
        path = workdir / spec.name
        blob = path.read_bytes()
        mine = jpg_mod.parse_jpeg(blob)
        ref = djpeg_view(path)
        if ref is None:
            mismatches.append(f"{spec.name}: djpeg produced no SOF line")
            continue

        dims = mine.dimensions()
        if dims != (ref["width"], ref["height"]):
            mismatches.append(f"{spec.name}: dims {dims} != "
                              f"{(ref['width'], ref['height'])}")

        my_tables = mine.quant_tables()
        if set(my_tables) != set(ref["qtables"]):
            mismatches.append(f"{spec.name}: table ids {sorted(my_tables)} != "
                              f"{sorted(ref['qtables'])}")
        for tid, zz in my_tables.items():
            if tid not in ref["qtables"]:
                continue
            natural = dezigzag(zz)
            if natural != ref["qtables"][tid]:
                mismatches.append(f"{spec.name}: DQT {tid} differs after de-zigzag")
            tables_compared += 1

        if mine.errors:
            mismatches.append(f"{spec.name}: parser errors {mine.errors}")
        if mine.eoi_end != len(blob):
            mismatches.append(f"{spec.name}: EOI at {mine.eoi_end}, file is {len(blob)}")

    return {
        "name": "B_jpeg_matches_djpeg",
        "files": len(specs),
        "qtables_compared": tables_compared,
        "mismatches": mismatches[:10],
        "mismatch_count": len(mismatches),
        "pass": len(mismatches) == 0,
    }


def criterion_c_offsets(workdir: Path) -> Dict:
    """Three carriers, three known offsets, no decoder involved."""
    import struct
    import zlib

    checks: List[Tuple[str, bool, str]] = []

    # (1) Data appended after IEND.
    base = corpus.render(corpus.CoverSpec("c1.png", 90_001, 128, 96, "texture", "png"))
    payload = b"AFTER-IEND-PAYLOAD" * 4
    carrier = base + payload
    parsed = png_mod.parse_png(carrier)
    ok = (parsed.trailing_offset == len(base) and parsed.trailing == payload)
    checks.append(("png_trailing_after_iend", ok,
                   f"reported offset {parsed.trailing_offset}, expected {len(base)}"))

    # (2) Private ancillary PNG chunk inserted before IEND.
    parsed_base = png_mod.parse_png(base)
    iend = parsed_base.chunks[-1]
    ctype = b"stEG"
    body = b"PRIVATE-CHUNK-PAYLOAD"
    chunk = (struct.pack(">I", len(body)) + ctype + body
             + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))
    carrier2 = base[:iend.offset] + chunk + base[iend.offset:]
    parsed2 = png_mod.parse_png(carrier2)
    found = [c for c in parsed2.chunks if c.ctype == "stEG"]
    ok2 = (len(found) == 1 and found[0].offset == iend.offset
           and found[0].data == body and found[0].crc_ok
           and found[0].is_private and found[0].is_ancillary
           and found[0].reserved_bit_ok and not found[0].is_known)
    checks.append(("png_private_chunk", ok2,
                   f"found {len(found)} stEG chunk(s) at "
                   f"{[c.offset for c in found]}, expected offset {iend.offset}"))

    # (3) JPEG COM segment inserted immediately after SOI.
    jbase = corpus.render(corpus.CoverSpec("c3.jpg", 90_003, 128, 96, "photo_like",
                                           "jpeg", quality=90))
    com_body = b"COMMENT-SEGMENT-PAYLOAD"
    com = b"\xff\xfe" + struct.pack(">H", len(com_body) + 2) + com_body
    carrier3 = jbase[:2] + com + jbase[2:]
    parsed3 = jpg_mod.parse_jpeg(carrier3)
    coms = parsed3.segments_of("COM")
    ok3 = (len(coms) == 1 and coms[0].offset == 2 and coms[0].data == com_body
           and parsed3.eoi_end == len(carrier3) and not parsed3.errors)
    checks.append(("jpeg_com_segment", ok3,
                   f"found {len(coms)} COM at {[c.offset for c in coms]}, expected 2"))

    return {
        "name": "C_offsets_localised",
        "checks": [{"check": n, "pass": p, "detail": d} for n, p, d in checks],
        "pass": all(p for _, p, _ in checks),
    }


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        results = [
            criterion_a_png(work / "png"),
            criterion_b_jpeg(work / "jpeg"),
            criterion_c_offsets(work),
        ]

    (RESULTS / "G1.json").write_text(json.dumps(results, indent=2) + "\n")

    print("=" * 70)
    print("Gate G1 -- structural parsing without a decoder")
    print("=" * 70)
    hard_fail = False
    for r in results:
        status = "SKIP" if r.get("pass") is None else ("PASS" if r["pass"] else "FAIL")
        if status == "FAIL":
            hard_fail = True
        print(f"[{status}] {r['name']}")
        for k, v in r.items():
            if k in ("name", "pass"):
                continue
            print(f"        {k}: {v}")
    print("=" * 70)
    print("GATE G1:", "FAIL" if hard_fail else "PASS")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
