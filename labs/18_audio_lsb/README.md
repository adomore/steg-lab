# Lab 18 -- Audio LSB: bit depth defeats the statistics, silence does not care

| | |
|---|---|
| Domain | audio |
| Algorithm | lsb-replacement |
| Detectors | `audio_silence_lsb` (structural), `audio_weighted_stego` (statistical) |
| Measured FPR | 0/16 clean at both 8 and 16 bits |
| Evidence ceiling | E4 -- sequential path, payload recovered 16/16 |

## Bit depth is the whole statistical story

An 8-bit sample spans 256 levels, so flipping its low bit moves it by 1/256 of
full scale. A 16-bit sample spans 65,536, so the same flip moves it by
1/65,536 -- forty-eight decibels quieter relative to the carrier.

Weighted Stego with a two-neighbour predictor, clean against stego at the same
relative payload:

| bit depth | clean | stego | ratio |
|---|---|---|---|
| 8-bit | 0.0130 | 0.2689 | **20.7x** |
| 16-bit | 1.1822 | 1.3253 | **1.1x** |

The estimator is unchanged; the carrier's precision is the only difference. At
16 bits the residual the detector is built on is buried, and this is not a
tuning problem -- it is arithmetic. Anything that raises a carrier's precision
buys the embedder the same protection.

## Silence does not care about bit depth

Audio has a structure images lack: passages of digital silence, where every
sample sits exactly at the silence level. LSB replacement turns those into a
stream of that level and one above it.

Two format details make or break this check, and both are the kind that fail
quietly:

**Silence is not always zero.** 8-bit WAV is *unsigned* with midpoint 128;
everything wider is signed with midpoint 0. Searching for zeros in an 8-bit
clip finds the waveform's most negative excursions and misses the silence
entirely.

**Look for near-silence, not silence.** The search is for samples within 1 of
the level rather than equal to it, because embedding is exactly what puts the
ones there. Looking for exact matches makes an embedded passage invisible to
the check meant to catch it.

## The discriminator that removed the false positives

A first version flagged any silent run containing non-level samples, and gave
2/16 false alarms on 8-bit clips -- at that quantiser resolution a genuinely
quiet musical passage is indistinguishable from silence by amplitude alone.

LSB replacement can only ever produce the level or one *above* it. A real quiet
passage crosses the level in both directions and therefore also contains
level - 1. Requiring the deviations to be one-sided took false positives to
**0/16 at both bit depths**.

## What it catches, and what it does not

| | 8-bit | 16-bit |
|---|---|---|
| clean false positives | 0/16 | 0/16 |
| detected, of clips containing silence | 4/12 | 7/12 |
| payload recovered byte-exact | 16/16 | 16/16 |

The misses are not a threshold problem. A 1200-byte payload occupies the first
9,600 samples of a 22,050-sample clip, so a silent passage further along is
never touched. Measured directly on one clip: 200 bytes gives E0, 1,200 gives a
finding. **The structural check fires only where the payload reaches the
silence**, and a clip with no silence at all is invisible to it -- 0/8 on
silence-free carriers, correctly.

That is the honest shape of a structural detector: decisive where it applies,
blind where it does not, and never guessing in between.

## The parser

`steganalysis.wav` walks the RIFF chunk stream without asking a decoder
anything, and agrees with Python's `wave` module on channels, rate, frame count
and every sample across 6 clips. RIFF leaks in the same three places as PNG and
JPEG -- a declared size with bytes past it, chunks nobody reads, and a `data`
chunk shorter than what follows it -- so the A-group habits transfer unchanged.

## Reproduce

```bash
python3 -m pytest tests/test_labs_f.py -q
```

## What it teaches

Two detectors on one carrier, and the carrier's precision defeats one of them
completely while leaving the other untouched. When a report says a technique
was not detected, the question is which detector was applied and whether the
carrier was one it can work on.

---

[Chinese version](README_zh.md)
