"""Lab 20 -- text carriers, where the false positives are the whole difficulty.

Every carrier so far had a property text does not: the hiding places were
bytes nothing legitimate needed. A chunk nobody registered, a segment no
decoder reads, silence that is exactly zero -- finding them was work, but once
found there was nothing to argue about.

Unicode is different. **The characters used to hide in text are characters that
do real linguistic work.** ZERO WIDTH NON-JOINER separates Persian and Urdu
morphemes; ZERO WIDTH JOINER builds emoji sequences and Devanagari conjuncts;
VARIATION SELECTOR-16 is what makes an emoji render as an emoji. A detector
that flags every invisible character reports every multilingual document ever
written, which is a detector with a 100% false-positive rate on exactly the
corpora that matter.

So this lab's content is not "find the invisible characters". It is: given that
invisible characters are everywhere and mostly innocent, what distinguishes
carrying from writing? Three signals, all contextual:

  * **runs** -- orthography places one joiner between two letters; payload bits
    arrive consecutively;
  * **script context** -- a ZWNJ between two ASCII letters has no orthographic
    job, because no script written in ASCII uses one;
  * **selector range** -- VS15 and VS16 are presentation selectors and are
    everywhere; VS17 upward exist for Ideographic Variation Sequences and are
    meaningless after a non-CJK base.

Domain    : text
Algorithm : zero-width / variation-selector / trailing-whitespace
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report, cap_without_baseline)

NAME = "text_unicode"
DOMAIN = "text"
ALGORITHM = "zero-width"

ZWSP = "\u200b"          # bit 0
ZWNJ = "\u200c"          # bit 1
ZWJ = "\u200d"
ZWNBSP = "\ufeff"
ZERO_WIDTH = {ZWSP, ZWNJ, ZWJ, ZWNBSP}

#: Presentation selectors. Ubiquitous and almost always innocent.
VS_PRESENTATION = {"\ufe0e", "\ufe0f"}
#: Ideographic variation selectors, U+E0100..U+E01EF. Legitimate only after a
#: CJK ideograph, and they carry a whole byte each, which makes them the
#: densest text channel in this lab by a wide margin.
VS_IDEOGRAPHIC_BASE = 0xE0100

#: A run of this many consecutive zero-width characters has no orthographic
#: reading in any script. One joiner between two letters is language; four in a
#: row is a bit field.
RUN_THRESHOLD = 3

#: Consecutive lines ending in whitespace before the pattern stops looking like
#: an editor's leftovers. Combined with the presence of trailing tabs, which
#: prose essentially never produces.
WHITESPACE_RUN = 16


def _is_ascii_letter(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


# --------------------------------------------------------------------------
# Embedding
# --------------------------------------------------------------------------

def embed_zero_width(cover: str, payload: bytes, anchor: str = " ") -> str:
    """Encode payload bits as a run of ZWSP/ZWNJ after the first anchor."""
    bits = "".join(f"{byte:08b}" for byte in payload)
    hidden = "".join(ZWSP if b == "0" else ZWNJ for b in bits)
    index = cover.find(anchor)
    if index < 0:
        return cover + hidden
    return cover[:index + 1] + hidden + cover[index + 1:]


def extract_zero_width(text: str) -> bytes:
    """No key: the alphabet is fixed and the run is contiguous."""
    bits = "".join("0" if ch == ZWSP else "1"
                   for ch in text if ch in (ZWSP, ZWNJ))
    usable = (len(bits) // 8) * 8
    return bytes(int(bits[i:i + 8], 2) for i in range(0, usable, 8))


def embed_variation_selectors(cover: str, payload: bytes) -> str:
    """One byte per selector, appended to the first character.

    U+E0100 + n encodes the byte n directly, so this channel carries eight bits
    per invisible codepoint against one for the zero-width alphabet. Density is
    exactly why it is worth detecting separately.
    """
    if not cover:
        raise ValueError("cover text is empty")
    tail = "".join(chr(VS_IDEOGRAPHIC_BASE + byte) for byte in payload)
    return cover[0] + tail + cover[1:]


def extract_variation_selectors(text: str) -> bytes:
    return bytes(ord(ch) - VS_IDEOGRAPHIC_BASE for ch in text
                 if VS_IDEOGRAPHIC_BASE <= ord(ch) <= VS_IDEOGRAPHIC_BASE + 0xFF)


def embed_trailing_whitespace(cover: str, payload: bytes) -> str:
    """SNOW-style: a space encodes 0 and a tab encodes 1 at end of line."""
    bits = "".join(f"{byte:08b}" for byte in payload)
    lines = cover.split("\n")
    if len(lines) < len(bits):
        raise ValueError(f"payload needs {len(bits)} lines, cover has {len(lines)}")
    out = []
    for i, line in enumerate(lines):
        out.append(line + (("\t" if bits[i] == "1" else " ")
                           if i < len(bits) else ""))
    return "\n".join(out)


def extract_trailing_whitespace(text: str, nbytes: int) -> bytes:
    bits = ""
    for line in text.split("\n"):
        if line.endswith("\t"):
            bits += "1"
        elif line.endswith(" "):
            bits += "0"
        else:
            break
    usable = min((len(bits) // 8) * 8, nbytes * 8)
    return bytes(int(bits[i:i + 8], 2) for i in range(0, usable, 8))


def embed(cover: str, payload: bytes, variant: str = "zero_width") -> str:
    if variant == "zero_width":
        return embed_zero_width(cover, payload)
    if variant == "variation_selectors":
        return embed_variation_selectors(cover, payload)
    if variant == "trailing_whitespace":
        return embed_trailing_whitespace(cover, payload)
    raise ValueError(f"unknown variant {variant}")


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def zero_width_runs(text: str) -> List[Tuple[int, int, str]]:
    """Return (start, length, surrounding-script) for each zero-width run."""
    runs: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(text):
        if text[i] in ZERO_WIDTH:
            start = i
            while i < len(text) and text[i] in ZERO_WIDTH:
                i += 1
            before = text[start - 1] if start > 0 else ""
            after = text[i] if i < len(text) else ""
            if before and after and _is_ascii_letter(before) and _is_ascii_letter(after):
                context = "ascii"
            elif before and after:
                context = "non-ascii"
            else:
                context = "edge"
            runs.append((start, i - start, context))
        else:
            i += 1
    return runs


def suspicious_selectors(text: str) -> int:
    """Ideographic variation selectors that do not follow a CJK ideograph."""
    count = 0
    for i, ch in enumerate(text):
        code = ord(ch)
        if not (VS_IDEOGRAPHIC_BASE <= code <= VS_IDEOGRAPHIC_BASE + 0xEF):
            continue
        base = ""
        j = i - 1
        while j >= 0 and VS_IDEOGRAPHIC_BASE <= ord(text[j]) <= VS_IDEOGRAPHIC_BASE + 0xEF:
            j -= 1
        if j >= 0:
            base = text[j]
        if not base or unicodedata.category(base) != "Lo" or ord(base) < 0x3000:
            count += 1
    return count


def trailing_whitespace_profile(text: str) -> Dict[str, int]:
    """Trailing whitespace is common; the SNOW pattern is not.

    Editors leave stray trailing spaces everywhere, and Markdown's hard-break
    convention is two trailing SPACES, so counting lines that end in whitespace
    flags ordinary documents. Two things separate an encoding from an accident:

      * **tabs.** Prose almost never ends a line with a tab; a space/tab
        alphabet needs them for every 1 bit.
      * **contiguity.** A payload occupies a prefix of consecutive lines,
        because that is the order it is written in. Stray whitespace is
        scattered.
    """
    lines = text.split("\n")
    tabs = sum(1 for line in lines if line.endswith("\t"))
    spaces = sum(1 for line in lines if line.endswith(" "))
    longest = run = 0
    for line in lines:
        if line and line[-1] in (" ", "\t"):
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return {"lines": len(lines), "trailing_tabs": tabs,
            "trailing_spaces": spaces, "longest_run": longest}


def trailing_whitespace_lines(text: str) -> int:
    profile = trailing_whitespace_profile(text)
    return profile["trailing_tabs"] + profile["trailing_spaces"]


def _as_text(data) -> Optional[str]:
    """Accept str or bytes, because the pipeline hands every lab bytes.

    Returning None rather than raising on undecodable input is the point: a
    binary carrier misrouted here must produce no finding, not an exception
    that aborts the stage and not a garbage decode that produces one.
    """
    if isinstance(data, str):
        return data
    try:
        return bytes(data).decode("utf-8")
    except (UnicodeDecodeError, TypeError, ValueError):
        return None


def analyse(text: str) -> Dict[str, object]:
    runs = zero_width_runs(text)
    long_runs = [r for r in runs if r[1] >= RUN_THRESHOLD]
    ascii_runs = [r for r in runs if r[2] == "ascii"]
    return {
        "zero_width_total": sum(r[1] for r in runs),
        "zero_width_runs": len(runs),
        "longest_run": max((r[1] for r in runs), default=0),
        "runs_over_threshold": len(long_runs),
        "runs_between_ascii_letters": len(ascii_runs),
        "suspicious_selectors": suspicious_selectors(text),
        "characters": len(text),
        **{f"ws_{k}": v for k, v in trailing_whitespace_profile(text).items()},
    }


def detect(text, name: str = "<carrier>",
           baseline: Optional[FalsePositiveBaseline] = None,
           payload_bytes: int = 0) -> Report:
    report = Report(carrier=name)
    decoded = _as_text(text)
    if decoded is None:
        return report
    text = decoded
    stats = analyse(text)

    # Zero-width. A run long enough to be a bit field, or one sitting between
    # two ASCII letters where no orthography would put it.
    if stats["runs_over_threshold"] or stats["runs_between_ascii_letters"]:
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = extract_zero_width(text) if level >= Evidence.E3 else None
        if payload:
            level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="text_zero_width",
            claim=(f"{stats['zero_width_total']} zero-width characters in "
                   f"{stats['zero_width_runs']} run(s), longest "
                   f"{stats['longest_run']}; "
                   f"{stats['runs_between_ascii_letters']} run(s) sit between "
                   f"ASCII letters, where no script places a joiner"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="zero-width" if level >= Evidence.E3 else None,
            payload=payload,
            baseline=baseline,
            detail=dict(stats),
        ))

    # Trailing whitespace. Needs both signals: tabs are what prose does not
    # produce, and a contiguous run is what a payload looks like.
    if stats["ws_trailing_tabs"] and stats["ws_longest_run"] >= WHITESPACE_RUN:
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = (extract_trailing_whitespace(text, payload_bytes or 64)
                   if level >= Evidence.E3 else None)
        if payload:
            level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="text_trailing_whitespace",
            claim=(f"{stats['ws_trailing_tabs']} line(s) end in a tab and "
                   f"{stats['ws_longest_run']} consecutive lines end in "
                   f"whitespace; prose leaves stray spaces, not runs of "
                   f"space-or-tab"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="trailing-whitespace" if level >= Evidence.E3 else None,
            payload=payload,
            baseline=baseline,
            detail={k: v for k, v in stats.items() if k.startswith("ws_")},
        ))

    if stats["suspicious_selectors"]:
        level = cap_without_baseline(Evidence.E3, baseline)
        payload = extract_variation_selectors(text) if level >= Evidence.E3 else None
        if payload:
            level = Evidence.E4
        report.add(Finding(
            carrier=name, level=level, detector="text_variation_selectors",
            claim=(f"{stats['suspicious_selectors']} ideographic variation "
                   f"selector(s) follow a base that is not a CJK ideograph, "
                   f"carrying one byte each"),
            domain=DOMAIN if level >= Evidence.E3 else None,
            algorithm="variation-selector" if level >= Evidence.E3 else None,
            payload=payload,
            baseline=baseline,
            detail={"suspicious_selectors": stats["suspicious_selectors"]},
        ))

    return report


def build_sample(cover: str, payload: bytes) -> str:
    return embed(cover, payload)
