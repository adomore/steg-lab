"""Tests for the documentation checkers themselves.

A checker that has never failed is an assumption, not a check. These tests
inject each kind of drift into a temporary tree and assert the checker sees
it -- and inject the shapes that must NOT fire, because a checker's own false
positive is worse than the drift it looks for: it trains people to override it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_checker(tmp_root: Path):
    """Import check-docs with ROOT pointed at a temporary tree."""
    spec = importlib.util.spec_from_file_location(
        "check_docs", ROOT / "scripts" / "check-docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_root
    return module


def write_pair(root: Path, stem: str, english: str, chinese: str) -> None:
    (root / f"{stem}.md").write_text(english, encoding="utf-8")
    (root / f"{stem}_zh.md").write_text(chinese, encoding="utf-8")


ALIGNED_EN = """# Title

## One

| a | b |
|---|---|
| 1 | 2 |

## Two

Text.
"""

ALIGNED_ZH = """# 标题

## 一

| 甲 | 乙 |
|---|---|
| 1 | 2 |

## 二

正文。
"""


def test_aligned_twins_pass(tmp_path):
    write_pair(tmp_path, "doc", ALIGNED_EN, ALIGNED_ZH)
    assert load_checker(tmp_path).check_twins() == []


def test_a_missing_translation_is_caught(tmp_path):
    (tmp_path / "solo.md").write_text("# Solo\n", encoding="utf-8")
    problems = load_checker(tmp_path).check_twins()
    assert any("no Chinese sibling" in p[1] for p in problems)


def test_a_section_added_on_one_side_is_caught(tmp_path):
    write_pair(tmp_path, "doc", ALIGNED_EN,
               ALIGNED_ZH + "\n## 只在中文里\n\n多出来的一节。\n")
    problems = load_checker(tmp_path).check_twins()
    assert any("section structure differs" in p[1] for p in problems)


def test_one_table_row_dropped_is_caught(tmp_path):
    """The commonest drift, and the one a +/-1 tolerance let through."""
    write_pair(tmp_path, "doc", ALIGNED_EN, ALIGNED_ZH.replace("| 1 | 2 |\n", ""))
    problems = load_checker(tmp_path).check_twins()
    assert any("table rows differ" in p[1] for p in problems)


def test_mathematical_notation_is_not_a_table_row(tmp_path):
    """|x| in prose counted as a table row and reported identical files as drifted.

    Measured on docs/theory/T6, whose two tables are the same and whose Chinese
    text discusses |x| having a kink at zero.
    """
    english = ALIGNED_EN + "\nThe function |x| has a kink at zero.\n"
    chinese = ALIGNED_ZH + "\n|x| 在零点有折点。\n"
    write_pair(tmp_path, "doc", english, chinese)
    assert load_checker(tmp_path).check_twins() == []


def test_headings_inside_code_fences_are_not_sections(tmp_path):
    """A shell transcript's '#' comment is not a section heading."""
    english = ALIGNED_EN + "\n```bash\n# a comment, not a heading\nls\n```\n"
    write_pair(tmp_path, "doc", english, ALIGNED_ZH)
    assert load_checker(tmp_path).check_twins() == []


def test_translated_heading_text_does_not_count_as_drift(tmp_path):
    """Only heading LEVELS are compared; the text is translated by design."""
    write_pair(tmp_path, "doc", ALIGNED_EN,
               ALIGNED_ZH.replace("## 一", "## 完全不同的标题文字"))
    assert load_checker(tmp_path).check_twins() == []


# ------------------------------------------- the single-language exemption

MARKED_SOLO = """<!-- twins:single-language a stated reason -->
# Solo
"""

UNMARKED_SOLO = """# Solo
"""

REASONLESS_SOLO = """<!-- twins:single-language -->
# Solo
"""

ZH_WITH_EXTRA_SECTION = ALIGNED_ZH + """
## 只在中文里

多出来的一节。
"""


def test_a_marked_single_language_document_needs_no_translation(tmp_path):
    """The GitHub landing page is Chinese on purpose and links to the English
    README. A translation pair of one language into itself is not a thing."""
    (tmp_path / "solo.md").write_text(MARKED_SOLO, encoding="utf-8")
    assert load_checker(tmp_path).check_twins() == []


def test_an_unmarked_single_language_document_is_still_caught(tmp_path):
    """The exemption must be opt-in, or it is not a rule any more."""
    (tmp_path / "solo.md").write_text(UNMARKED_SOLO, encoding="utf-8")
    problems = load_checker(tmp_path).check_twins()
    assert any("no Chinese sibling" in p[1] for p in problems)


def test_the_marker_needs_a_reason(tmp_path):
    """An exemption with no reason is a bare override, and overrides get
    copied to the next file by someone who never learns why."""
    (tmp_path / "solo.md").write_text(REASONLESS_SOLO, encoding="utf-8")
    problems = load_checker(tmp_path).check_twins()
    assert any("no Chinese sibling" in p[1] for p in problems)


def test_the_marker_cannot_silence_drift_between_real_twins(tmp_path):
    """The escape hatch must not become a way to mute the checker.

    It applies only where the sibling is genuinely absent. A document that HAS
    a sibling is still structure-compared, marker or no marker -- otherwise the
    cheapest way to green a red build would be to paste the marker in.
    """
    write_pair(tmp_path, "doc", MARKED_SOLO + ALIGNED_EN, ZH_WITH_EXTRA_SECTION)
    problems = load_checker(tmp_path).check_twins()
    assert any("section structure differs" in p[1] for p in problems)


def test_a_single_language_document_is_in_neither_pairing_count(tmp_path):
    """docs_en and docs_zh exist to express the pairing invariant. An exempt
    page counted in docs_en makes the two disagree, which reads as translation
    drift when none has happened."""
    write_pair(tmp_path, "doc", ALIGNED_EN, ALIGNED_ZH)
    (tmp_path / "solo.md").write_text(MARKED_SOLO, encoding="utf-8")
    for sub in ("labs", "gates", "tests"):
        (tmp_path / sub).mkdir(exist_ok=True)
    (tmp_path / "docs" / "theory").mkdir(parents=True, exist_ok=True)
    facts = load_checker(tmp_path).repo_facts()
    assert facts["docs_en"] == facts["docs_zh"] == 1


# ------------------------------------------------- withheld-detector count

def _skeleton(root: Path) -> None:
    for sub in ("labs", "gates", "tests", "steganalysis"):
        (root / sub).mkdir(exist_ok=True)
    (root / "docs" / "theory").mkdir(parents=True, exist_ok=True)


def test_unvalidated_detectors_are_counted_from_the_suffix(tmp_path):
    """MAINTAINERS states this count in words, and it went stale for a release.

    Sample Pair Analysis was withheld, then rederived and promoted into
    DETECTORS, and the sentence saying "two are in the module" survived
    unchanged. Counting the suffix is what turns that into a red bar.
    """
    _skeleton(tmp_path)
    (tmp_path / "steganalysis" / "detectors.py").write_text(
        "def working(x):\n    return x\n\n\n"
        "def calibrated_hcf_com_UNVALIDATED(x):\n    return x\n",
        encoding="utf-8")
    assert load_checker(tmp_path).repo_facts()["unvalidated_detectors"] == 1


def test_promoting_a_detector_turns_a_stale_claim_red(tmp_path):
    """The drift this key exists to catch, injected."""
    _skeleton(tmp_path)
    (tmp_path / "steganalysis" / "detectors.py").write_text(
        "def only_one_UNVALIDATED(x):\n    return x\n", encoding="utf-8")
    write_pair(tmp_path, "doc",
               ALIGNED_EN + "\nTwo are withheld.\n<!-- claim:unvalidated_detectors=2 -->\n",
               ALIGNED_ZH + "\n两个被扣住。\n<!-- claim:unvalidated_detectors=2 -->\n")
    problems = load_checker(tmp_path).check_claims()
    assert any("unvalidated_detectors=2 but repo has 1" in p[1] for p in problems)
