#!/usr/bin/env python3
"""Six documentation checkers.

The twins checker enforces EN/ZH lockstep structurally, not just by file
existence: heading levels in sequence and table row counts must match. Its own
behaviour is tested in tests/test_check_docs.py, including the shapes that must
NOT fire.

Five of these are inherited from sc-fuzz-lab. The sixth, `commands`, is new,
and it exists because of a specific recurring failure: in the smart-contract
lab, a documented command used a flag that did not exist. It survived two
merges and six documents because nothing ever checked whether the commands
in the prose could actually run. The same class of bug then recurred three
more times with shell-unsafe angle-bracket placeholders.

That was logged as GAP N-4 and deferred. Here it ships on day one, because
a knowledge base whose commands do not run is worse than no knowledge base:
it costs the reader time before it fails.

Checks
  links     -- every relative Markdown link resolves to a file that exists
  twins     -- every EN document has a _zh sibling and vice versa
  quotes    -- ZH documents keep code, commands and identifiers in English
  claims    -- numeric claims about the repo match the repo
  headings  -- EN/ZH document pairs have the same heading structure
  commands  -- shell commands in fenced blocks use real flags and safe
               placeholders, and referenced scripts exist

Run:  python3 scripts/check-docs.py [--only links,commands]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {".git", "__pycache__", "target", "generated", "reference",
             ".pytest_cache", "results"}

Problem = Tuple[str, str]   # (file, message)


def markdown_files() -> List[Path]:
    out = []
    for p in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


# ------------------------------------------------------------------- links

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def check_links() -> List[Problem]:
    problems: List[Problem] = []
    for md in markdown_files():
        for m in LINK_RE.finditer(md.read_text(encoding="utf-8")):
            target = m.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (md.parent / target).resolve()
            if not resolved.exists():
                problems.append((str(md.relative_to(ROOT)),
                                 f"broken link -> {target}"))
    return problems


# ------------------------------------------------------------------- twins

def _section_headings(path: Path) -> List[str]:
    """Heading lines outside fenced code blocks.

    Fences matter: a shell transcript containing a `#` comment is not a
    section, and counting it would make the two languages disagree whenever
    one of them shows more of a command's output.
    """
    out: List[str] = []
    fenced = False
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.startswith("#"):
            out.append(line.split(" ", 1)[0])       # the level, not the text
    return out


def _table_rows(path: Path) -> int:
    fenced = False
    count = 0
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        stripped = line.strip()
        # A table row has a closing pipe and at least two cells. Testing only
        # for a leading pipe counted a paragraph that happens to begin with
        # mathematical notation -- "|x| has a kink at zero" -- as a table row,
        # and reported the two languages as drifted when both tables were
        # identical. A checker's own false positive is worse than the drift it
        # looks for, because it trains people to override it.
        if (not fenced and stripped.startswith("|") and stripped.endswith("|")
                and stripped.count("|") >= 3):
            count += 1
    return count


#: A document may opt out of the pairing rule, but only by saying so in its own
#: text and giving a reason. The one case today is a platform landing page:
#: GitHub renders .github/README.md for visitors, this project's readers are
#: Chinese-speaking, and that page links to the English README rather than
#: duplicating it -- a translation pair of one language into itself is not a
#: thing. An exemption written in the file is visible to whoever edits the
#: file; one kept in a SKIP list somewhere else is not.
#:
#: Deliberately narrow: it applies ONLY when the sibling is genuinely absent.
#: A file that HAS a sibling is still structure-compared, marker or no marker,
#: so this cannot be used to silence the drift the checker exists to catch.
TWINS_EXEMPT_MARKER = "<!-- twins:single-language"


def single_language_reason(path: Path) -> str:
    """The stated reason a document has no translation, or "" if none."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(TWINS_EXEMPT_MARKER) and stripped.endswith("-->"):
            return stripped[len(TWINS_EXEMPT_MARKER):-3].strip()
    return ""


def check_twins() -> List[Problem]:
    """Both halves exist AND say the same things in the same order.

    Existence alone is not lockstep. A translated document drifts by having a
    section added on one side only, or a measured table updated in English and
    left stale in Chinese -- and a reader of the Chinese version then carries
    away a number this repository has already disproved. That has happened here
    twice, in gap rows, and both times the drift was invisible until somebody
    read the two files side by side.

    Checked: the sequence of heading LEVELS (not their text, which is
    translated) and the number of table rows. Prose length is deliberately not
    checked -- Chinese is denser and a length rule would produce noise.
    """
    problems: List[Problem] = []
    files = {p.relative_to(ROOT) for p in markdown_files()}
    for rel in sorted(files):
        name = rel.name
        if name.endswith("_zh.md"):
            twin = rel.with_name(name[:-6] + ".md")
            if twin not in files:
                problems.append((str(rel), f"no English sibling {twin.name}"))
            continue

        twin = rel.with_name(name[:-3] + "_zh.md")
        if twin not in files:
            if not single_language_reason(ROOT / rel):
                problems.append((str(rel), f"no Chinese sibling {twin.name}"))
            continue

        en_headings = _section_headings(ROOT / rel)
        zh_headings = _section_headings(ROOT / twin)
        if en_headings != zh_headings:
            problems.append((
                str(rel),
                f"section structure differs from {twin.name}: "
                f"{len(en_headings)} headings ({''.join(h[0] for h in en_headings[:0])}"
                f"{'/'.join(en_headings)}) against {len(zh_headings)} "
                f"({'/'.join(zh_headings)})"))

        # Exact, not within one. A tolerance of one row lets through exactly
        # the commonest drift there is -- a measured table updated on one side
        # and a row dropped from the other -- which was the case this checker
        # was written to catch. Verified by deliberately removing one row and
        # watching the tolerant version stay green.
        en_rows = _table_rows(ROOT / rel)
        zh_rows = _table_rows(ROOT / twin)
        if en_rows != zh_rows:
            problems.append((
                str(rel),
                f"table rows differ from {twin.name}: {en_rows} against "
                f"{zh_rows}; a measured table updated on one side only"))
    return problems


# ------------------------------------------------------------------ quotes

CJK = re.compile(r"[\u4e00-\u9fff]")


def check_quotes() -> List[Problem]:
    """Code fences and inline code in ZH documents stay in English.

    Translating a command or an identifier makes it unrunnable and
    ungreppable. Prose gets translated; machinery does not.
    """
    problems: List[Problem] = []
    for md in markdown_files():
        if not md.name.endswith("_zh.md"):
            continue
        text = md.read_text(encoding="utf-8")
        for block in re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S):
            # Comments inside a fence may be translated; code may not.
            for line in block.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                if CJK.search(line):
                    problems.append((str(md.relative_to(ROOT)),
                                     f"CJK inside a code fence: {stripped[:60]}"))
        for inline in re.findall(r"`([^`\n]+)`", text):
            if CJK.search(inline):
                problems.append((str(md.relative_to(ROOT)),
                                 f"CJK inside inline code: {inline[:60]}"))
    return problems


# ------------------------------------------------------------------ claims

CLAIM_RE = re.compile(r"<!--\s*claim:([a-z_]+)=(\d+)\s*-->")


def repo_facts() -> Dict[str, int]:
    labs = sorted((ROOT / "labs").glob("[0-9][0-9]_*"))
    theory = sorted((ROOT / "docs" / "theory").glob("T[0-9]*.md"))
    gates = sorted((ROOT / "gates").glob("g[0-9]*.py"))
    tests = 0
    for t in (ROOT / "tests").glob("test_*.py"):
        tests += len(re.findall(r"^def test_", t.read_text(encoding="utf-8"), re.M))
    # docs_en and docs_zh exist to express the pairing invariant, so a document
    # that opted out of pairing belongs in neither count. Without this a
    # single-language page inflates docs_en and the two numbers stop matching,
    # which reads as translation drift when none has happened.
    paired = [p for p in markdown_files() if not single_language_reason(p)]
    en = [p for p in paired if not p.name.endswith("_zh.md")]
    zh = [p for p in paired if p.name.endswith("_zh.md")]
    return {
        "labs": len(labs),
        "theory_chapters": len([t for t in theory if not t.name.endswith("_zh.md")]),
        "gates": len(gates),
        "test_functions": tests,
        "docs_en": len(en),
        "docs_zh": len(zh),
    }


def check_claims() -> List[Problem]:
    """Numeric claims are tagged and verified, so they cannot drift silently.

    Write `<!-- claim:labs=6 -->` next to a sentence that says "six labs".
    When the count changes, this goes red instead of the prose going stale.
    """
    facts = repo_facts()
    problems: List[Problem] = []
    for md in markdown_files():
        for m in CLAIM_RE.finditer(md.read_text(encoding="utf-8")):
            key, claimed = m.group(1), int(m.group(2))
            if key not in facts:
                problems.append((str(md.relative_to(ROOT)),
                                 f"unknown claim key '{key}'"))
            elif facts[key] != claimed:
                problems.append((str(md.relative_to(ROOT)),
                                 f"claim {key}={claimed} but repo has {facts[key]}"))
    return problems


# ---------------------------------------------------------------- headings

def headings(text: str) -> List[int]:
    return [len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s+\S", text, re.M)]


def check_headings() -> List[Problem]:
    problems: List[Problem] = []
    for md in markdown_files():
        if md.name.endswith("_zh.md"):
            continue
        twin = md.with_name(md.name[:-3] + "_zh.md")
        if not twin.exists():
            continue
        a = headings(md.read_text(encoding="utf-8"))
        b = headings(twin.read_text(encoding="utf-8"))
        if a != b:
            problems.append((str(md.relative_to(ROOT)),
                             f"heading structure differs from {twin.name}: "
                             f"{len(a)} vs {len(b)} headings"))
    return problems


# ---------------------------------------------------------------- commands

FENCE_RE = re.compile(r"```(?:bash|sh|console|shell)\n(.*?)```", re.S)

# Placeholders that a shell would try to interpret. `<ADDR>` is a redirect.
UNSAFE_PLACEHOLDER = re.compile(r"<[A-Za-z_][A-Za-z0-9_ -]*>")

KNOWN_TOOLS = {
    "python3", "python", "pytest", "cargo", "make", "bash", "sh", "pip",
    "pip3", "pipx", "git", "cd", "ls", "cat", "mkdir", "cp", "mv", "rm",
    "echo", "export", "chmod", "tar", "curl", "wget", "apt", "apt-get",
    "sudo", "steghide", "stegseek", "zsteg", "binwalk", "foremost",
    "exiftool", "pngcheck", "djpeg", "jpegtran", "convert", "identify",
    "ffmpeg", "sox", "tshark", "unzip", "zip", "xxd", "hexdump", "file",
    "strings", "grep", "find", "java", "gem", "go", "rustup", "source",
}


def _local_flag_check(cmd: str) -> List[str]:
    """Verify flags for this repo's own Python entry points via --help."""
    issues: List[str] = []
    m = re.match(r"python3?\s+(\S+\.py)\s*(.*)", cmd)
    if not m:
        return issues
    script = ROOT / m.group(1)
    if not script.exists():
        return [f"script does not exist: {m.group(1)}"]
    flags = re.findall(r"(?<!\S)(--[a-zA-Z][\w-]*)", m.group(2))
    if not flags:
        return issues
    proc = subprocess.run([sys.executable, str(script), "--help"],
                          capture_output=True, text=True, cwd=ROOT)
    helptext = proc.stdout + proc.stderr
    for flag in flags:
        if flag not in helptext:
            issues.append(f"{m.group(1)} has no flag {flag}")
    return issues


def check_commands() -> List[Problem]:
    problems: List[Problem] = []
    makefile = (ROOT / "Makefile")
    make_targets = set()
    if makefile.exists():
        make_targets = set(re.findall(r"^([a-zA-Z][\w-]*):",
                                      makefile.read_text(encoding="utf-8"), re.M))

    for md in markdown_files():
        rel = str(md.relative_to(ROOT))
        for block in FENCE_RE.findall(md.read_text(encoding="utf-8")):
            for raw in block.splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                line = line.lstrip("$ ").strip()
                if not line:
                    continue

                for ph in UNSAFE_PLACEHOLDER.findall(line):
                    problems.append((rel, f"shell-unsafe placeholder {ph} in: {line[:70]}"))

                tool = line.split()[0]
                if tool not in KNOWN_TOOLS and "=" not in tool:
                    problems.append((rel, f"unknown tool '{tool}' in: {line[:70]}"))

                if tool == "make":
                    for target in line.split()[1:]:
                        if target.startswith("-") or "=" in target:
                            continue
                        if make_targets and target not in make_targets:
                            problems.append((rel, f"no Makefile target '{target}'"))

                for issue in _local_flag_check(line):
                    problems.append((rel, issue))

                for token in re.findall(r"(?:scripts|gates|corpus|labs)/\S+\.(?:py|sh)", line):
                    if not (ROOT / token).exists():
                        problems.append((rel, f"referenced file does not exist: {token}"))
    return problems


CHECKS = {
    "links": check_links,
    "twins": check_twins,
    "quotes": check_quotes,
    "claims": check_claims,
    "headings": check_headings,
    "commands": check_commands,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated subset of checks")
    ap.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = ap.parse_args()

    selected = ([c.strip() for c in args.only.split(",") if c.strip()]
                if args.only else list(CHECKS))
    unknown = [c for c in selected if c not in CHECKS]
    if unknown:
        print(f"unknown check(s): {', '.join(unknown)}")
        return 2

    all_problems: Dict[str, List[Problem]] = {}
    for name in selected:
        all_problems[name] = CHECKS[name]()

    if args.json:
        print(json.dumps({k: [list(p) for p in v] for k, v in all_problems.items()},
                         indent=2))
        return 1 if any(all_problems.values()) else 0

    failed = False
    print("=" * 70)
    print("check-docs")
    print("=" * 70)
    for name in selected:
        problems = all_problems[name]
        status = "PASS" if not problems else "FAIL"
        if problems:
            failed = True
        print(f"[{status}] {name}: {len(problems)} problem(s)")
        for f, msg in problems[:12]:
            print(f"        {f}: {msg}")
        if len(problems) > 12:
            print(f"        ... and {len(problems) - 12} more")
    print("-" * 70)
    facts = repo_facts()
    print("repo facts: " + ", ".join(f"{k}={v}" for k, v in facts.items()))
    print("=" * 70)
    print("CHECK-DOCS:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
