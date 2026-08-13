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
