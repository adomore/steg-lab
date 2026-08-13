# T7 -- Forensic workflow and decision-making

> Gate: **G7** -- `python3 gates/g7_capstone.py` -- PASSED

## 7.1 The workflow is an order of questions

Everything up to here produces detectors. T7 is about the order they run in and
the discipline of not answering a question before its prerequisites are met.

1. **Structural accounting first**, because it is deterministic. Either every
   byte has a reason to exist or it does not; nothing needs a threshold, and a
   hit produces a payload rather than a probability.
2. **Then statistical estimation**, which needs a threshold, which needs a
   baseline.
3. **Baselines are measured on same-source clean carriers before any verdict
   is recorded**, not afterwards to justify one.

## 7.2 The pipeline, made executable

`steganalysis.pipeline` is that order written down so it can be run on a
carrier nobody has told it about. It takes bytes, a label and a set of
baselines. It has no parameter through which ground truth could arrive, which
is checked structurally rather than trusted: an interface that *can* leak the
answer eventually will.

A stage that raises is recorded as a failed stage rather than aborting the
analysis -- a carrier that breaks one parser is exactly the carrier the others
should still see -- but the failure is reported, because "the JPEG stage
crashed" and "the JPEG stage found nothing" are different facts.

## 7.3 Dispatch is not an optimisation

G7 failed its no-over-claims criterion on the first run: three of seven clean
carriers were reported at E3, every one of them in the `jpeg-dct` domain.

The cause was not a detector. Every statistical detector was running on every
carrier, so lab 14's operating point -- measured on grayscale JPEGs at quality
90 -- was being applied to colour JPEGs, and lab 07's, measured on grayscale
PNGs, to anything at all.

A threshold is a property of the carrier. T4 section 4.7 measured a
false-positive rate moving from 0% to 25% from that mistake, and T5 section 5.6
measured a classifier going from P_E 0.140 to chance. The pipeline was
committing the error the rest of the course exists to warn about.

So the pipeline now routes by container type, and refuses to apply a
grayscale-calibrated threshold to a colour carrier -- determined by parsing the
`IHDR` colour type or the SOF component count, not by a filename. Over-claims
went from three to zero and accuracy from 0.90 to 1.00. Declining to run a
detector is a result too.

## 7.4 What the capstone measured

30 trials, answers sealed, 7 clean and 23 carrying across five recipes and four
domains.

| | called clean | called carrying |
|---|---|---|
| **clean** | 7 | 0 |
| **carrying** | 0 | 23 |

Domain named correctly: 23/23. No stage failed on any carrier.

The accuracy figure is the least interesting number there. What matters is
which cell is empty.

## 7.5 The errors do not cost the same

Criterion C -- zero clean carriers at E3 or above -- is graded separately from
accuracy and it is the criterion that can fail the whole gate on its own.

A missed payload costs an investigation a lead. A false confirmation costs
somebody their defence. A run that misses half the payloads and never
over-claims passes criterion C; one that catches everything and over-claims
once does not.

This is also why P_E -- the field's standard figure, which weights false alarms
and missed detections equally -- is the right default for comparing methods in
a paper and the wrong one for any real case. Section 5.4 makes the same point
from the other end.

## 7.6 What a report may and may not say

The checklist covers this; three items are worth repeating because they are the
ones that get lost.

**State the level, the detector, the threshold and the baseline together.** A
number without its baseline is not a result. The evidence ladder makes this
mechanical: `assert_reportable()` raises rather than warns, so an E3 finding
without a measured baseline and an identified domain cannot be recorded at all.

**"No payload found" is not "no payload present."** An active channel may have
destroyed one. Gate G0 measured a JPEG recompression at quality 90 taking an
LSB payload to a bit error rate of 0.498 and steghide extraction to 12/12
failures. Say which was tested.

**Record what was not tested.** Absent coverage is not absent risk, and a
report that does not say what it skipped implies it skipped nothing. This
repository cannot detect LSB matching without training a classifier on the
source (T5), cannot name F5 against nsF5 (lab 14), and has no detector for
palette or audio carriers at all.

## 7.7 Further reading

NIST SP 800-86 on integrating forensic technique into incident response;
ISO/IEC 27037 and 27042 on identification, preservation and interpretation of
digital evidence; SWGDE's image analysis guidelines; and the Daubert standard,
which is why "what is your error rate?" is a question you will be asked under
oath and why the evidence ladder demands a measured baseline rather than a
plausible one.

---

Previous: [T6 -- Deep-learning steganalysis](T6_deep_learning.md) |
[Chinese version](T7_forensic_workflow_zh.md)
