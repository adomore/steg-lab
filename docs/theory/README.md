# Theory layer

Eight chapters, T0 through T7. Each one ends in a **gate**: a falsifiable
acceptance criterion, implemented as a runnable script under `gates/`. A
chapter is not finished when it reads well; it is finished when its gate
passes on this machine.

Gates may include criteria that must **fail**. T4's gate requires that RS
and Sample Pair Analysis collapse against LSB matching, because a course
that only demonstrates successes teaches an analyst to expect them.

## Status

| Chapter | Topic | Gate | Status |
|---|---|---|---|
| T0 | Problem definition and threat model | G0 | PASS |
| T1 | Carriers and embedding domains | G1 | PASS |
| T2 | Classical embedding algorithms | G2 | PASS |
| T3 | Adaptive embedding and distortion minimisation | G3 | PASS |
| T4 | Statistical steganalysis | G4 | PASS |
| T5 | Feature sets and ensemble classification | G5 | PASS |
| T6 | Deep-learning steganalysis | G6 | PASS |
| T7 | Forensic workflow and decision-making | G7 | PASS |

## Reading order

T0 and T1 are prerequisites for everything. After that, T2 and T4 pair
naturally (an attack and its detection), as do T3 and T5. T6 depends on T5.
T7 depends on all of them, and its gate is the capstone.

## Chapters

- [T0 -- Problem definition and threat model](T0_threat_model.md)
- [T1 -- Carriers and embedding domains](T1_carriers_and_domains.md)
- [T2 -- Classical embedding algorithms](T2_classical_algorithms.md)
- [T3 -- Adaptive embedding and distortion minimisation](T3_adaptive_embedding.md)
- [T4 -- Statistical steganalysis](T4_statistical_steganalysis.md)
- [T5 -- Feature sets and ensemble classification](T5_feature_sets.md)
- [T6 -- Deep-learning steganalysis](T6_deep_learning.md)
- [T7 -- Forensic workflow and decision-making](T7_forensic_workflow.md)

---

[Chinese version](README_zh.md)
