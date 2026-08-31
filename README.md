# steg-lab

A steganalysis knowledge base for Kali Linux: theory with falsifiable
acceptance criteria, and labs whose detectors are measured rather than
described.

**Version 1.1.0.** Seventeen labs covering every carrier class -- container,
spatial, JPEG-DCT, palette, audio, text, network, video and three filesystems --
eight theory chapters with eight gates passing, an executable forensic pipeline,
and a Rust triage sideline differentially tested against the Python reference.

Every parser here is cross-validated against an independent implementation:
pngcheck, djpeg, the stdlib `wave` module, tshark, ffmpeg, mtools, debugfs and
ntfscat. Every threshold is measured on the carrier it applies to, and where a
check has no power it declines rather than producing a number. What the
repository cannot do is in [GAP_ANALYSIS.md](GAP_ANALYSIS.md), including the
things it refuses to attempt and why.
<!-- claim:labs=17 -->
<!-- claim:gates=8 -->

## The rule this repository is built around

Smart-contract auditing has `No PoC, no High`: a severity claim is backed by
an executable exploit or it is downgraded. Steganalysis needs the same shape
of rule, but its verdicts are statistical rather than deterministic, so the
backing artefact is different:

> **No extraction and no baseline, no verdict.**

Concretely, a finding may be reported at E3 or above only if it carries a
false-positive rate measured on clean carriers **from the same source**.
`steganalysis.evidence.Finding.assert_reportable()` raises rather than
warns, because a warning gets ignored under deadline pressure.

## The evidence ladder

| Level | Meaning | Requires |
|---|---|---|
| E0 | no anomaly | -- |
| E1 | suspicious, but normal processing could explain it | nothing |
| E2 | statistical anomaly | a measured baseline |
| E3 | steganography confirmed | baseline + identified domain |
| E4 | payload extracted (ciphertext counts) | the payload bytes |
| E5 | key or passphrase recovered | reproducible full extraction |

E1 exists so an analyst has somewhere honest to put "this looks odd but I
cannot rule out normal processing".

## Layout

```
docs/theory/      T0-T7 chapters, each gated
docs/cases/       real-incident narratives
labs/NN_name/     one carrier family per lab: embed, detect, README
steganalysis/     shared library: parsers, evidence ladder, corpus
gates/            runnable acceptance criteria
rust/stegscan/    container triage at scale, zero dependencies
corpus/           seeded generation; no image bytes in the repository
scripts/          setup, verification, doc checks, differential test
tests/            pytest suite
```

## Quick start

```bash
bash scripts/setup-kali.sh
bash scripts/verify-toolchain.sh
python3 corpus/generate.py
python3 -m pytest tests -q
python3 gates/g0_wardens.py
python3 gates/g1_parsers.py
```

Or via make:

```bash
make setup verify corpus test gates
```

## What P0 measured

| Result | Value |
|---|---|
| Passive warden, payload bit error rate | 0.0 |
| Active warden vs LSB, median BER at JPEG q90 | 0.498 |
| Active warden vs steghide, extraction failures | 12/12 |
| Malicious warden, forgeries accepted | 12/12 |
| PNG parser vs pngcheck, chunk mismatches | 0 of 162 |
| JPEG parser vs djpeg, quantisation table mismatches | 0 of 100 |
| Rust vs Python differential, field mismatches | 0 of 210 files x 9 fields |
| Rust triage speedup over Python | 4.0x |
| Structural polyglot detector, false positives | 0/500 |
| Signature-scan detector, false positives | 2/500 |
| F5 matrix-encoding efficiency vs theory, worst error | 0.47% |
| Embedding efficiency F5 loses to shrinkage | 45.3% |
| Weighted Stego AUC vs LSB replacement at 0.25 bpp | 1.000 |
| Same detectors vs LSB matching, worst deviation from chance | 0.086 |
| Weighted Stego payload estimate, mean absolute error | 0.031-0.044 |
| Same detector, matched vs mismatched baseline source, FPR | 0% vs 25% |
| SPAM686 + ensemble vs LSB matching at 1.0 bpp, P_E | 0.140 |
| Best structural detector on the same task, P_E | 0.450 |
| Same classifier under cover source mismatch, P_E | 0.487 (chance) |
| JPEG encoder round trip, coefficient mismatches | 0 |
| Jsteg detection, payloads 200-1100 bytes | 10/10, 0/30 false positives |
| Jsteg payload length estimate, 800 bytes true | 793 estimated |
| STC distortion vs the rate-distortion bound at h=12 | +7.93% |
| HILL change density, textured : smooth (uniform control 0.98) | 1.84 |

And on real BOSSbase covers, which is where the numbers above stop being
provisional:

| Result on BOSSbase 1.01 | Value |
|---|---|
| Weighted Stego AUC vs LSB replacement at 0.05 bpp (synthetic: 0.594) | **0.882** |
| chi-square clean-cover mean p-value (synthetic: 0.944) | **0.129** |
| RS and WS false positives at their 95%-TPR thresholds | 0/200 each |
| SPAM686 + ensemble P_E vs LSB matching at 1.0 bpp | 0.125 |
| P_E after a cross-camera shift (canon_eos_7d to nikon_d70) | 0.160 |
| P_E after a single resample of the same images | 0.500 |
| HILL+STC vs LSB matching at 0.4 bpp, P_E | **0.344 vs 0.198** |
| STC gap to the rate-distortion bound at h=12, keyed embedding path | **5.98%** |
| F5 detection by calibration, clean false positives | 0/24 |
| Blind capstone: 30 sealed trials, over-claims on clean | **0** |
| Blind capstone: embedding domain named correctly | 23/23 |
| Weighted Stego response to LSB audio, 8-bit vs 16-bit carrier | **20.7x vs 1.1x** |
| Audio silence check, false positives at both bit depths | 0/16 |
| Text detectors on a legitimate multilingual corpus | 0/8 false positives |
| Spread text adversary: longest run vs runs between ASCII letters | 1 vs 48 |
| Network: three covert channels, detection and extraction | 12/12 each, 0/12 false positives |
| Timing channel: top-two gap share, background vs channel | 0.03 vs >0.5 |
| pcap parser vs tshark 4.2.2 | 0 mismatches in 6,400 field comparisons |
| Video temporal LSB: clean peak vs payload peak | 0.005 vs 0.084 |
| Video: payload and signal after MPEG-4 re-encode | both destroyed |
| Progressive JPEG coefficients vs the baseline encoding of the same image | bit-identical |
| FAT file slack: non-zero bytes on a freshly formatted volume | 0 |
| Deleted-file residue vs a deliberate payload in slack | indistinguishable |
| NTFS resident ADS: reads back byte-exact, contiguous in the image | yes / **no** (fixups) |
| Sample Pair Analysis payload estimate, true 0.20 / 0.40 | 0.208 / 0.391 |
| Blind capstone across all nine carrier domains | 34/40, **0 over-claims** |
| CNN cost of removing the fixed high-pass layer, BOSSbase 128px | **P_E 0.163 -> 0.493 (chance)** |
| CNN against SPAM686 + ensemble on the same split, BOSSbase | 0.257 against 0.170 |
| STC gap vs cost dynamic range, everything else fixed | 60x range: 533% -> 7.5x range: **64%** |

The polyglot rows are the same lab; so are the two LSB rows. Both gaps are
the argument for the evidence ladder.

## Three things this repository refuses to do

**Ship binary carriers.** The corpus is generated from seeds and pinned by
SHA-256, which makes "same source" a checkable property rather than a claim.

**Ship commands it has not run.** `scripts/check-docs.py` validates that
flags in the documentation exist, that placeholders are shell-safe, and that
referenced scripts are present. This closes a bug class that recurred four
times in a sibling project.

**Report a verdict without a baseline.** See above.

## Documentation

- [Learning path](LEARNING_PATH.md) -- what to read in what order
- [Theory layer](docs/theory/README.md) -- T0-T7 and their gates
- [Analyst checklist](STEGANALYSIS_CHECKLIST.md) -- the casework order,
  every carrier family covered
- [Threat model template](THREAT_MODEL_TEMPLATE.md)
- [Getting started](GETTING_STARTED.md) -- half an hour, ending with a
  payload you hid and then found
- [Tool practice](docs/TOOL_PRACTICE.md) -- how each tool's output can be
  read wrong, measured while cross-validating this repository's parsers
- [Resources](RESOURCES.md) -- tools, corpora, literature
- Reference corpora: `bash scripts/get-corpora.sh`, then
  `python3 scripts/register-corpus.py`
- [Maintainers](MAINTAINERS.md) -- how to resume work
- [Gap analysis](GAP_ANALYSIS.md) -- what is knowingly missing

---

[Chinese version](README_zh.md)
