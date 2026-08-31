# Learning path

First day here instead: [Getting started](GETTING_STARTED.md).

Theory and practice are interleaved deliberately. Reading T4 without having
built a detector produces someone who can name RS analysis; building
detectors without T4 produces someone who runs tools. Neither is the goal.

## The spine

| Stage | Read | Build | Gate |
|---|---|---|---|
| 0 | T0 threat model | reproduce the three wardens | G0 |
| 1 | T1 carriers | labs 01-06, container layer | G1 |
| 2 | T2 classical algorithms | LSB-R, LSB-M, Jsteg, F5 from scratch | G2 |
| 3 | T4 statistical detection | chi-square, RS, SPA, WS from scratch | G4 |
| 4 | T3 adaptive embedding | STC encoder, S-UNIWARD costs | G3 |
| 5 | T5 features and ensembles | SPAM, SRM subset, FLD ensemble | G5 |
| 6 | T6 deep learning | a CPU-trainable detector | G6 |
| 7 | T7 forensic workflow | the blind capstone | G7 |

T2 before T4 and T3 before T5 is not negotiable: you cannot build a detector
for an algorithm you have not implemented, because you will not know which
of its properties are essential and which are incidental.

## What stages 0-1 leave you able to do

Both gates pass. What you should be able to do having finished them:

- state which warden class a scenario involves, and say what that rules in
  and out
- parse a PNG or JPEG structurally without an image library
- answer "does every byte in this file have a reason to exist?"
- measure a detector's false-positive rate before quoting its result

The habit from T1 section 1.6 is the transferable part: parse, account,
then compare the format's two descriptions of itself.

## What P0 deferred, and what became of it

**Filesystem slack and NTFS alternate data streams.** The outline placed
this in the A group. It needs a real mounted volume, which the build
environment did not have, and a lab whose commands cannot run is worse than
no lab. Deferred to P3 with a hardware prerequisite recorded; lab 04 took its
slot. The prerequisite turned out to be wrong. `mkfs.vfat`, `debugfs` and
`ntfscp` build and populate images as ordinary files, so lab 23 shipped in P3
covering FAT, ext4 and NTFS without mounting anything or needing privileges.
A blocked prerequisite is worth re-testing before it is worth waiting for.

**Statistical detection of any kind.** Everything in P0 is deterministic.
That is a deliberate ordering choice, not an omission: the accounting habit
is easier to acquire when every answer is exactly right or exactly wrong.

## A note on the corpus

Synthetic covers are sufficient for stages 0-1 and insufficient from stage 3
onward. Structure does not care about sensor noise; statistical detectors
key on almost nothing else. A detector tuned on synthetic textures will look
excellent here and fall over on evidence.

Stages 3 and beyond therefore run against BOSSbase, BOWS2 and ALASKA2, by
reference. Run `bash scripts/get-corpora.sh` for sources and licensing.

## Status

All eight stages complete at v1.0.0. Gates G0 through G7 pass.

Four findings from the sequence are worth carrying forward, because each one
changed how the rest of the repository was built.

**The synthetic corpus was shown inadequate by measurement, not argument.**
The chi-square attack fired on 64 of 80 clean synthetic covers and on 18 of 200
real ones; Weighted Stego's AUC at 0.05 bpp went from 0.594 to 0.882 when the
carriers became photographs. Everything statistical here carries the corpus it
was measured on.

**LSB replacement is detectable and LSB matching is not, by the same
detectors.** Stage 3 measured that as a required failure; stage 5 closed it
with SPAM686 and an ensemble, P_E 0.125 on real covers against 0.405 for the
structural estimators. A detector that stops failing on matching is broken, not
improved.

**Cover source mismatch is two effects an order of magnitude apart.** Swapping
the camera costs a few points; putting the evidence through one resize costs
everything, P_E 0.163 to 0.500. Casework almost always involves the second.

**Whenever a payload is smaller than its carrier, measure along the embedding
order.** Three labs arrived at this independently -- Jsteg's windowed
chi-square, the palette test, the video frame-pair check -- after each first
measured a global statistic and found nothing.

---

[Chinese version](LEARNING_PATH_zh.md)
