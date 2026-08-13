# Lab 22 -- Video: the carrier is redundant with itself

| | |
|---|---|
| Domain | video |
| Algorithms | frame-lsb, container-append |
| Detectors | `video_temporal_lsb`, `video_trailing_data` |
| Measured FPR | 0/8 on noise-free same-source clips |
| Detection | 8/8 at 400 bytes; extraction 8/8 |
| Evidence ceiling | E4 |

## What video has that a stack of images does not

Consecutive frames of a static scene carry the *same pixel values*, so their
least significant bits are the same bits. Embedding randomises them. The
per-pixel LSB flip rate between consecutive frames therefore separates a
background that was left alone from one that was written into -- and no
single-image detector can see this, because it needs two frames to exist.

It is lab 18's silent passage in another medium: find the part of the carrier
that should be exactly predictable, and check whether it is.

| | clean | with payload |
|---|---|---|
| median pair flip rate | 0.0000 | 0.0000 |
| **peak pair flip rate** | **0.0054** | **0.0835** |

## Per pair, not per clip

The first version averaged the flip rate over the whole clip and measured
0.0076 on a carrier it should have found instantly. A payload occupies a prefix
of the embedding order, so it lands in the first frames and every later pair is
untouched; averaging over twenty-three pairs divides the signal by twenty-three.
Measured per pair, the same payload gives 0.083 in the pair it actually
occupies.

That is the third time in this repository the same correction has been needed
-- lab 13's windowed chi-square and lab 10's windowed palette test are the same
fix -- and it generalises: **a global statistic is swamped by the untouched
majority whenever a payload is smaller than its carrier.**

## The threshold is measured

Over 16 clean noise-free clips the peak pair flip rate never exceeded 0.00814.
The operating point is 0.02, about 2.5x that ceiling:

| payload | peak flip rate | against the clean ceiling |
|---|---|---|
| 100 bytes | 0.0217 | 2.7x |
| 400 bytes | 0.0835 | 10.3x |
| 2,000 bytes | 0.3722 | 45.7x |

## Sensor noise defeats it, and the detector says so

A clip with even mild sensor noise has a static-region flip rate of **0.487**
before anything is embedded. The low bit is already random; there is nothing
left to disturb.

So the detector checks applicability before producing a verdict: if the clip's
own median flip rate is above 0.05, it reports at E1 that the check has no
power on this carrier and stops. Four of the twelve corpus clips are noisy, and
all four decline correctly rather than returning a number.

Declining to run is a result. The same move appears in the pipeline's refusal
to apply a grayscale-calibrated threshold to a colour carrier, and in lab 21's
IP-ID channel capping at E1 because a randomising stack is indistinguishable.

## The headline limitation, measured

Re-encoding the stego clip with MPEG-4 at quality 3:

| | value |
|---|---|
| static-region median flip rate after re-encode | 0.0858 |
| detector verdict | E1 -- declines, noise floor exceeded |
| **payload survives** | **no** |

Every lossy codec rewrites pixels between frames on its own, which destroys the
payload and the signal together. **This works on lossless video and nothing
else.** A report saying "no steganography found" in an H.264 file has said much
less than it appears to -- and by gate G0's taxonomy, any transcoding pipeline
is an active warden whether or not anyone intended it.

## Reproduce

```bash
python3 -m pytest tests/test_labs_i.py -q
```

## The parser

`steganalysis.avi` writes and walks uncompressed AVI without asking a decoder
anything. Cross-validated against ffprobe 6.x on dimensions and frame count,
and against ffmpeg's own decoder **pixel-for-pixel** -- BI_RGB stores rows
bottom-up and channels as BGR, and getting either wrong yields an array that
looks like video and is mirrored or colour-swapped.

## What it teaches

Redundancy is an asset the analyst holds and the embedder cannot spend. Wherever
a format repeats itself -- across frames, across a silent passage, across a
palette's sorted neighbours -- there is a prediction to make and a deviation to
measure.

---

[Chinese version](README_zh.md)
