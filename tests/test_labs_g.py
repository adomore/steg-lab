"""G-group tests: text carriers.

The important tests here are the negative ones. Every other lab could assume
its hiding place was bytes nothing legitimate needed; in text the hiding places
are characters doing linguistic work, so a detector is only worth having if it
stays quiet on real multilingual writing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.common import load_lab  # noqa: E402
from steganalysis.evidence import Evidence, FalsePositiveBaseline  # noqa: E402

PROSE = ("The committee reviewed the quarterly submissions carefully and "
         "recommended several substantive amendments before publication. "
         "Members noted that the previous methodology understated variance "
         "in the smaller regional samples. ") * 3

#: Real writing in which invisible characters are doing their jobs.
LEGITIMATE = {
    "english": PROSE,
    "persian": "او می\u200cرود و کتاب\u200cها را می\u200cخواند و سپس بازمی\u200cگردد.",
    "emoji": "\U0001F468\u200D\U0001F469\u200D\U0001F467 and \u2764\ufe0f\U0001F44D",
    "devanagari": "हिन्दी में क\u200cष और क\u200dष दोनों प्रयोग होते हैं।",
    "cjk_ivs": "\u908A" + chr(0xE0100) + "\u9089" + chr(0xE0101) + " in a CJK document",
    "diacritics": "café naïve résumé — ordinary Latin, no joiners.",
    "bom": "\ufeffhttps://example.org/path",
}


@pytest.mark.parametrize("name", sorted(LEGITIMATE))
def test_legitimate_unicode_is_not_reported(name):
    """A detector that flags real multilingual writing is worthless."""
    lab = load_lab("20_text_unicode")
    text = LEGITIMATE[name]
    assert lab.detect(text, name, baseline=None).verdict == Evidence.E0


def test_zero_width_round_trips_and_is_detected():
    lab = load_lab("20_text_unicode")
    data = b"lab20 zero width payload"
    stego = lab.embed(PROSE, data, variant="zero_width")
    assert lab.extract_zero_width(stego) == data
    assert lab.detect(stego, "s", baseline=None).verdict >= Evidence.E1


def test_spread_adversary_is_caught_by_script_context_not_run_length():
    """Two independent signals; defeating one walks into the other."""
    lab = load_lab("20_text_unicode")
    bits = "".join(f"{b:08b}" for b in b"hidden")
    out, k = [], 0
    for i, ch in enumerate(PROSE):
        out.append(ch)
        if (k < len(bits) and ch.isascii() and ch.isalpha()
                and i + 1 < len(PROSE) and PROSE[i + 1].isascii()
                and PROSE[i + 1].isalpha()):
            out.append(lab.ZWSP if bits[k] == "0" else lab.ZWNJ)
            k += 1
    stego = "".join(out)

    stats = lab.analyse(stego)
    assert stats["longest_run"] == 1, "the spread adversary makes no runs"
    assert stats["runs_over_threshold"] == 0, "so run length must find nothing"
    assert stats["runs_between_ascii_letters"] > 20
    assert lab.detect(stego, "s", baseline=None).verdict >= Evidence.E1


def test_variation_selectors_carry_a_byte_each():
    lab = load_lab("20_text_unicode")
    data = b"dense"
    stego = lab.embed(PROSE, data, variant="variation_selectors")
    assert len(stego) - len(PROSE) == len(data)
    assert lab.extract_variation_selectors(stego) == data
    assert lab.detect(stego, "s", baseline=None).verdict >= Evidence.E1


def test_presentation_selectors_are_not_flagged():
    """VS15 and VS16 are ubiquitous and innocent; VS17 upward are not."""
    lab = load_lab("20_text_unicode")
    assert lab.analyse("\u2764\ufe0f text \u2764\ufe0e")["suspicious_selectors"] == 0


def test_trailing_whitespace_needs_tabs_and_contiguity():
    lab = load_lab("20_text_unicode")
    lines = "\n".join(f"line {i} of the document" for i in range(80))
    stego = lab.embed(lines, b"snow", variant="trailing_whitespace")
    assert lab.extract_trailing_whitespace(stego, 4) == b"snow"
    assert lab.detect(stego, "s", baseline=None, payload_bytes=4).verdict >= Evidence.E1

    markdown = "\n".join((f"line {i}  " if i % 7 == 0 else f"line {i}")
                         for i in range(80))
    assert lab.detect(markdown, "md", baseline=None).verdict == Evidence.E0


def test_reaches_e4_with_a_baseline():
    lab = load_lab("20_text_unicode")
    data = b"payload recovered without a key"
    stego = lab.embed(PROSE, data, variant="zero_width")
    baseline = FalsePositiveBaseline("text_zero_width", 8, 0, 0.0,
                                     "8 legitimate multilingual documents")
    report = lab.detect(stego, "s", baseline=baseline)
    assert report.verdict == Evidence.E4
    assert report.findings[0].payload == data


def test_whitespace_capacity_is_enforced():
    lab = load_lab("20_text_unicode")
    with pytest.raises(ValueError, match="payload needs"):
        lab.embed("one\ntwo\nthree", b"too much", variant="trailing_whitespace")
