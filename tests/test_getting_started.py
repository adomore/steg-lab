"""The getting-started guide's code, executed verbatim.

A guide is the first thing a newcomer runs and the last thing anyone re-reads,
so it is where stale examples do the most damage: someone whose first command
fails concludes the repository is broken, not the documentation. The snippets
below are copied from GETTING_STARTED.md, including the numbers it promises.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis import corpus, pipeline  # noqa: E402
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402


def test_hide_then_find_without_a_baseline_stops_at_e1():
    """The guide's central demonstration: found, said so, refused to hand over."""
    cover = corpus.render(corpus.CoverSpec("cover.png", 1, 128, 128,
                                           "photo_like", "png"))
    lab = load_lab("01_trailing_data")
    stego = lab.embed(cover, b"MEET AT NOON")

    report = lab.detect(stego, "stego.png", baseline=None)
    assert report.verdict == Evidence.E1
    assert report.findings[0].payload is None


def test_a_measured_baseline_takes_it_to_e4_with_the_payload():
    """The guide promises 0 of 12 false positives and E4. Both are asserted."""
    cover = corpus.render(corpus.CoverSpec("cover.png", 1, 128, 128,
                                           "photo_like", "png"))
    lab = load_lab("01_trailing_data")
    stego = lab.embed(cover, b"MEET AT NOON")

    clean = [corpus.render(corpus.CoverSpec(f"c{i}.png", 100 + i, 128, 128,
                                            "photo_like", "png"))
             for i in range(12)]
    false_positives = sum(1 for c in clean
                          if lab.detect(c, "c", baseline=None).verdict
                          >= Evidence.E1)
    assert false_positives == 0, "the guide states 0 of 12"

    baseline = FalsePositiveBaseline("trailing_data", 12, false_positives, 0.0,
                                     "12 same-source clean PNGs")
    report = lab.detect(stego, "stego.png", baseline=baseline)
    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == b"MEET AT NOON"


def test_the_pipeline_snippet_runs_and_renders():
    cover = corpus.render(corpus.CoverSpec("cover.png", 1, 128, 128,
                                           "photo_like", "png"))
    stego = load_lab("01_trailing_data").embed(cover, b"MEET AT NOON")
    rendered = pipeline.render(pipeline.analyse(stego, "stego.png"))
    assert "verdict" in rendered
    assert pipeline.analyse(cover, "cover.png").verdict == Evidence.E0


def test_the_shell_commands_the_guide_opens_with_succeed():
    """A newcomer's first command failing reads as 'the repository is broken'."""
    for script in ("scripts/check-crossval.py", "scripts/check-docs.py"):
        result = subprocess.run([sys.executable, str(ROOT / script)],
                                capture_output=True, cwd=ROOT)
        assert result.returncode == 0, (script, result.stdout[-400:])
