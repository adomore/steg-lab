"""The claims in docs/TOOL_PRACTICE.md, asserted rather than described.

Every number in that document was measured on a real tool. A document that
records tool behaviour goes stale the moment a distribution upgrades the tool,
and prose does not fail a build. These tests do.

Each skips cleanly when its tool is absent, and the skip is visible through
scripts/check-crossval.py rather than passing silently as green.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis import corpus  # noqa: E402


def png(tmp_path: Path, name: str = "c.png") -> Path:
    path = tmp_path / name
    path.write_bytes(corpus.render(corpus.CoverSpec(name, 1, 64, 64,
                                                    "photo_like", "png")))
    return path


def jpeg(tmp_path: Path, name: str = "c.jpg") -> Path:
    path = tmp_path / name
    path.write_bytes(corpus.render(corpus.CoverSpec(name, 1, 64, 64,
                                                    "photo_like", "jpeg")))
    return path


@pytest.mark.skipif(shutil.which("pngcheck") is None, reason="pngcheck absent")
def test_pngcheck_exit_code_cannot_distinguish_corruption_from_hiding(tmp_path):
    """Documented: exit 2 means 'something structural', not 'a payload'."""
    clean = png(tmp_path)
    assert subprocess.run(["pngcheck", str(clean)],
                          capture_output=True).returncode == 0

    appended = tmp_path / "appended.png"
    appended.write_bytes(clean.read_bytes() + b"APPENDED-SECRET")
    hidden = subprocess.run(["pngcheck", str(appended)], capture_output=True)

    truncated = tmp_path / "broken.png"
    truncated.write_bytes(clean.read_bytes()[:-40])
    broken = subprocess.run(["pngcheck", str(truncated)], capture_output=True)

    assert hidden.returncode == 2
    assert broken.returncode == hidden.returncode, (
        "the point of the doc entry: the same code for both")


@pytest.mark.skipif(shutil.which("steghide") is None, reason="steghide absent")
def test_steghide_exit_code_conflates_wrong_password_with_no_payload(tmp_path):
    """Documented: 1 means either, and only the output file separates them."""
    cover = jpeg(tmp_path)
    secret = tmp_path / "s.txt"
    secret.write_bytes(b"secret payload\n")
    stego = tmp_path / "st.jpg"
    subprocess.run(["steghide", "embed", "-cf", str(cover), "-ef", str(secret),
                    "-sf", str(stego), "-p", "pw", "-q", "-f"],
                   check=True, capture_output=True)

    def extract(carrier: Path, password: str, out: Path) -> int:
        return subprocess.run(
            ["steghide", "extract", "-sf", str(carrier), "-xf", str(out),
             "-p", password, "-q", "-f"], capture_output=True).returncode

    good = tmp_path / "good.bin"
    assert extract(stego, "pw", good) == 0
    assert good.read_bytes() == b"secret payload\n"

    wrong = extract(stego, "wrong", tmp_path / "a.bin")
    absent = extract(cover, "pw", tmp_path / "b.bin")
    assert wrong == absent == 1, "the documented conflation"
    assert not (tmp_path / "a.bin").exists()
    assert not (tmp_path / "b.bin").exists()


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool absent")
def test_exiftool_deletion_destroys_the_artefact(tmp_path):
    """Documented: -all= is a correct outcome and a dangerous habit.

    It removes the payload, which in an examination means it removed evidence.
    Asserted so the warning in the checklist has something behind it.
    """
    from steganalysis.evidence import Evidence
    lab = load_lab("03_metadata")
    carrier = tmp_path / "meta.png"
    carrier.write_bytes(lab.embed(png(tmp_path).read_bytes(),
                                  b"PAYLOAD-IN-TEXT-CHUNK"))
    # The detector, not a string search: lab 03 encodes what it embeds, so
    # grepping for the plaintext finds nothing before OR after and would
    # "confirm" the claim without ever testing it.
    assert lab.detect(carrier.read_bytes(), "m",
                      baseline=None).verdict >= Evidence.E1

    subprocess.run(["exiftool", "-all=", "-overwrite_original", str(carrier)],
                   check=True, capture_output=True)
    assert lab.detect(carrier.read_bytes(), "m",
                      baseline=None).verdict == Evidence.E0


def test_a_tool_negative_is_not_a_carrier_negative():
    """Documented: steghide detects steghide, not steganography.

    No external tool needed -- the claim is about scope, and lab 13 embeds a
    Jsteg payload that no steghide run would ever report.
    """
    from steganalysis.evidence import Evidence
    lab = load_lab("13_jsteg_jpeg")
    cover = corpus.render(corpus.CoverSpec("j.jpg", 3, 256, 256,
                                           "photo_like", "jpeg", quality=90))
    stego = lab.embed(cover, b"x" * 700)
    assert lab.detect(stego, "s", baseline=None).verdict >= Evidence.E1
