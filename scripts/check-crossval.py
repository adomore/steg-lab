#!/usr/bin/env python3
"""Report which cross-validations the test suite would skip on this machine.

Every hand-written parser here is checked against an independent
implementation, and each of those tests is guarded by `pytest.mark.skipif`.
That guard is correct -- the suite must run on a machine without the tools --
but it means **a skipped cross-validation reports the same green as a passing
one.** This makes the difference visible.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: (tool, file, description, probe). The probe RUNS the tool, because being on
#: PATH is not the same as working: on Kali a `djpeg` that decodes perfectly
#: well printed verbose output the gate could not parse, so the cross-check
#: would have skipped while this script said RUNS. Locating a binary is the
#: check that is easy to write, not the one that answers the question.
def _probe_pngcheck(tmp: Path) -> bool:
    from steganalysis import corpus
    png = tmp / "p.png"
    png.write_bytes(corpus.render(corpus.CoverSpec("p.png", 1, 32, 32,
                                                   "flat", "png")))
    out = subprocess.run(["pngcheck", "-v", str(png)],
                         capture_output=True, text=True)
    return "IHDR" in out.stdout + out.stderr


def _probe_djpeg(tmp: Path) -> bool:
    from steganalysis import corpus
    jpg = tmp / "j.jpg"
    jpg.write_bytes(corpus.render(corpus.CoverSpec("j.jpg", 1, 32, 32,
                                                   "photo_like", "jpeg")))
    out = subprocess.run(["djpeg", "-verbose", "-verbose", "-outfile",
                          "/dev/null", str(jpg)], capture_output=True, text=True)
    text = (out.stdout + out.stderr).lower()
    return "quantization table" in text


def _probe_tshark(tmp: Path) -> bool:
    from steganalysis.pcap import TrafficSpec, render_traffic
    cap = tmp / "c.pcap"
    cap.write_bytes(render_traffic(TrafficSpec("c.pcap", 1, packets=20,
                                               seconds=2.0)))
    out = subprocess.run(["tshark", "-r", str(cap), "-T", "fields",
                          "-e", "ip.proto"], capture_output=True, text=True)
    return out.returncode == 0 and out.stdout.strip() != ""


def _probe_ffmpeg(tmp: Path) -> bool:
    from steganalysis.avi import VideoSpec, render_video
    avi = tmp / "v.avi"
    avi.write_bytes(render_video(VideoSpec("v.avi", 1, frames=4)))
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(avi),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True)
    return out.returncode == 0 and len(out.stdout) == 4 * 72 * 96 * 3


def _probe_mkfs(tmp: Path) -> bool:
    img = tmp / "d.img"
    subprocess.run(["dd", "if=/dev/zero", f"of={img}", "bs=1M", "count=16"],
                   capture_output=True)
    out = subprocess.run(["mkfs.vfat", "-F", "16", "-s", "8", str(img)],
                         capture_output=True)
    return out.returncode == 0 and img.stat().st_size == 16 * 1024 * 1024


def _probe_mcopy(tmp: Path) -> bool:
    import os
    img = tmp / "m.img"
    subprocess.run(["dd", "if=/dev/zero", f"of={img}", "bs=1M", "count=16"],
                   capture_output=True)
    if subprocess.run(["mkfs.vfat", "-F", "16", "-s", "8", str(img)],
                      capture_output=True).returncode != 0:
        return False
    src = tmp / "a.txt"
    src.write_bytes(b"probe\n")
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
    out = subprocess.run(["mcopy", "-i", str(img), str(src), "::/A.TXT"],
                         capture_output=True, env=env)
    return out.returncode == 0


CROSS_CHECKS = [
    ("pngcheck", "gates/g1_parsers.py", "PNG chunk walk vs pngcheck",
     _probe_pngcheck),
    ("djpeg", "gates/g1_parsers.py", "JPEG segments and tables vs djpeg",
     _probe_djpeg),
    ("tshark", "tests/test_labs_h.py", "pcap fields and DNS names vs tshark",
     _probe_tshark),
    ("ffmpeg", "tests/test_labs_i.py", "AVI frames vs ffmpeg, pixel for pixel",
     _probe_ffmpeg),
    ("mkfs.vfat", "tests/test_labs_j.py", "FAT geometry vs mkfs/mdir",
     _probe_mkfs),
    ("mcopy", "tests/test_labs_j.py", "FAT directory entries vs mtools",
     _probe_mcopy),
]
#: These need no external tool: the reference is inside Python or is arithmetic.
ALWAYS_ON = [
    ("stdlib wave", "tests/test_labs_f.py", "WAV samples vs the wave module"),
    ("pixel DCT", "tests/test_core.py", "JPEG DC vs a DCT of the decoded pixels"),
    ("baseline JPEG", "tests/test_core.py",
     "progressive coefficients vs the baseline encoding"),
]


def main() -> int:
    print("=" * 72)
    print("Cross-validation coverage on this machine")
    print("=" * 72)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    broken, absent = [], []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for tool, where, what, probe in CROSS_CHECKS:
            if shutil.which(tool) is None:
                absent.append(tool)
                state = "SKIP"
                note = f"(needs {tool} -- not installed)"
            else:
                try:
                    works = probe(tmp)
                except Exception:                     # noqa: BLE001
                    works = False
                if works:
                    state = "RUNS"
                    note = f"(needs {tool} -- present and working)"
                else:
                    broken.append(tool)
                    state = "SKIP"
                    note = f"(needs {tool} -- PRESENT BUT UNUSABLE HERE)"
            print(f"  [{state}] {what}")
            print(f"         {where}  {note}")
    missing = absent + broken
    print()
    for _tool, where, what in ALWAYS_ON:
        print(f"  [RUNS] {what}")
        print(f"         {where}  (no external tool)")
    print()
    print("=" * 72)
    if missing:
        print(f"{len(missing)} cross-validation(s) will SKIP.")
        if absent:
            print(f"  not installed : {', '.join(absent)}")
            print("  fix           : bash scripts/setup-kali.sh")
        if broken:
            print(f"  present but unusable: {', '.join(broken)}")
            print("  These are the dangerous ones: the tool is on PATH, so a")
            print("  check that only looks for the binary reports RUNS while")
            print("  the comparison never happens.")
        print("The suite will still report green either way.")
        return 1
    print("Every cross-validation runs on this machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
