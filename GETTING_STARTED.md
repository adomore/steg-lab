# Getting started

Half an hour, ending with a payload you hid and then found, and one number that
explains why this repository is built the way it is.

This is not the reading order -- that is [the learning path](LEARNING_PATH.md).
It is not the casework order either -- that is
[the checklist](STEGANALYSIS_CHECKLIST.md). This is the first day.

## Install

```bash
bash scripts/setup-kali.sh
python3 scripts/verify-toolchain.sh 2>/dev/null || bash scripts/verify-toolchain.sh
```

On anything other than Kali, install the Python stack from
`requirements.txt` and whatever your package manager calls `pngcheck`,
`libjpeg-progs`, `dosfstools` and `mtools`.

Then find out what will silently not run:

```bash
python3 scripts/check-crossval.py
```

Every hand-written parser here is checked against an independent tool, and each
of those tests skips cleanly when its tool is missing. **A skipped
cross-validation reports the same green as a passing one**, so this script
prints RUNS or SKIP for each and exits non-zero if any would skip.

## Prove the repository works before trusting it

```bash
python3 -m pytest tests -q
python3 scripts/check-docs.py
python3 gates/g0_wardens.py
```

The gates are the acceptance criteria for the theory chapters. A chapter is not
finished when it reads well; it is finished when its gate passes.

## Hide something, then find it

Five commands, and the fourth one is the point.

```python
from steganalysis import corpus
from labs.common import load_lab

cover = corpus.render(corpus.CoverSpec("cover.png", 1, 128, 128,
                                       "photo_like", "png"))
lab = load_lab("01_trailing_data")
stego = lab.embed(cover, b"MEET AT NOON")

report = lab.detect(stego, "stego.png", baseline=None)
print(report.verdict)                     # E1
print(report.findings[0].payload)         # None
```

The payload is 12 bytes past the PNG's `IEND` marker. The detector found it,
said so, and **refused to hand it over**. That is the rule this repository is
built around, and it is enforced in code rather than recommended in prose.

Now measure a baseline and run it again:

```python
from steganalysis.evidence import FalsePositiveBaseline

clean = [corpus.render(corpus.CoverSpec(f"c{i}.png", 100 + i, 128, 128,
                                        "photo_like", "png"))
         for i in range(12)]
false_positives = sum(1 for c in clean
                      if lab.detect(c, "c", baseline=None).verdict >= 1)
# measured: 0 of 12

baseline = FalsePositiveBaseline("trailing_data", 12, false_positives, 0.0,
                                 "12 same-source clean PNGs")
report = lab.detect(stego, "stego.png", baseline=baseline)
print(report.verdict)                     # E4
print(report.findings[0].payload)         # b'MEET AT NOON'
```

**E1 to E4, and the payload arrives.** Nothing about the carrier changed. What
changed is that the claim now carries a false-positive rate measured on
carriers from the same source, which is the difference between a suspicion and
a finding.

## Run the whole pipeline on an unknown file

```python
from steganalysis import pipeline

result = pipeline.analyse(open("stego.png", "rb").read(), "stego.png")
print(pipeline.render(result))
```

The pipeline routes by container type, runs the structural labs before the
statistical ones, and declines to apply a threshold calibrated on one carrier
kind to another. On a clean carrier it reports E0 and says nothing else.

## Where to go next

| you want | read |
|---|---|
| the order to learn things in | [LEARNING_PATH.md](LEARNING_PATH.md) |
| what to do with a real artefact | [STEGANALYSIS_CHECKLIST.md](STEGANALYSIS_CHECKLIST.md) |
| how each tool can mislead you | [docs/TOOL_PRACTICE.md](docs/TOOL_PRACTICE.md) |
| the theory, each chapter with a gate | [docs/theory/](docs/theory/README.md) |
| what this repository still cannot do | [GAP_ANALYSIS.md](GAP_ANALYSIS.md) |

## Three habits worth taking from here

**Measure the baseline before the verdict.** Not after, to justify one. Every
threshold in this repository is a property of the carrier it was measured on,
and quoting one across sources is the commonest way to be confidently wrong.

**A check with no power should decline, not produce a number.** Lab 22 refuses
to run on video whose sensor noise has already randomised the low bit; lab 21
caps the IP-ID channel at E1 because a randomising network stack is
indistinguishable from a payload. Declining is a result.

**Record what you did not test.** Absent coverage is not absent risk, and a
report that does not say what it skipped implies it skipped nothing.

---

[Chinese version](GETTING_STARTED_zh.md)
