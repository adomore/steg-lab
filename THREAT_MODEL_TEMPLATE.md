# Threat model template

Fill this in before analysis, not after. The purpose is to make the
assumptions explicit while they are still cheap to change.

## 1. Channel

| Field | Value |
|---|---|
| Carrier format(s) | |
| Transport | |
| Transformations in transit | |
| Warden class | passive / active / malicious |
| Justification for that class | |

If the carrier transited a platform that re-encodes (most messaging and
social platforms do), the warden is **active** whether or not anyone
intended it. That changes what a negative result means.

## 2. Source characterisation

| Field | Value |
|---|---|
| Acquisition device | |
| Processing chain | |
| Encoder and settings | |
| Clean carriers available from this source | yes / no, count |
| If no: what is the nearest available source, and how does it differ | |

Everything in section 4 is invalid without this section.

## 3. Adversary

| Field | Value |
|---|---|
| Assumed capability | |
| Assumed tooling | off-the-shelf / modified / bespoke |
| Does the payload carry its own encryption | |
| Does the payload carry its own authentication | |
| Key material available to the analyst | |

A payload that is encrypted before embedding caps the realistic outcome at
E4. Recovering ciphertext is a complete result; say so rather than implying
a failure.

## 4. Detection plan

| Layer | Detector | Threshold | Baseline source | Measured FPR |
|---|---|---|---|---|
| container | | | | |
| spatial | | | | |
| jpeg-dct | | | | |
| metadata | | | | |

Empty cells in the last two columns cap that row at E1.

## 5. What this analysis will not cover

List explicitly. Absent coverage is not absent risk, and a report that does
not say what it skipped implies it skipped nothing.

## 6. Decision

| Field | Value |
|---|---|
| Highest defensible evidence level | |
| What would raise it | |
| Operational recommendation | analyse further / destroy channel / no action |

---

[Chinese version](THREAT_MODEL_TEMPLATE_zh.md)
