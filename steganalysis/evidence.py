"""The evidence ladder, and the rule that makes it binding.

Smart-contract auditing has `No PoC, no High`: a severity claim is backed
by an executable exploit or it is downgraded.  Steganalysis needs the same
shape of rule, but its verdicts are statistical rather than deterministic,
so the backing artefact is different.

Here the rule is:

    No extraction and no baseline, no verdict.

Concretely, a Finding may be reported at level E3 or above only if it
carries a FalsePositiveBaseline measured on clean carriers from the *same*
source.  Levels E1 and E2 exist precisely so that an analyst has somewhere
honest to put "this looks odd but I cannot rule out normal processing".

`Finding.assert_reportable()` raises instead of warning.  A warning would
be ignored under deadline pressure; an exception stops the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional


class Evidence(IntEnum):
    """Confidence ladder for a steganalysis verdict."""

    E0 = 0  # no anomaly observed
    E1 = 1  # structural anomaly, but normal processing could explain it
    E2 = 2  # statistical anomaly with a measured false-positive baseline
    E3 = 3  # embedding domain and algorithm family identified
    E4 = 4  # payload extracted (ciphertext counts)
    E5 = 5  # key or passphrase recovered, full extraction reproducible

    @property
    def label(self) -> str:
        return {
            0: "no anomaly",
            1: "suspicious (explainable)",
            2: "anomalous (baselined)",
            3: "steganography confirmed",
            4: "payload confirmed",
            5: "key recovered",
        }[int(self)]


#: Levels at or above which a baseline is mandatory before reporting.
BASELINE_REQUIRED_FROM = Evidence.E2

#: Levels that constitute a positive claim of steganography.
CONFIRMED_FROM = Evidence.E3


class UnsupportedVerdict(Exception):
    """Raised when a Finding claims more than its evidence supports."""


@dataclass
class FalsePositiveBaseline:
    """How often this detector fires on carriers known to be clean.

    `n_clean` must be the number of *same-source* clean carriers.  A
    baseline measured on a different camera, a different resampling chain
    or a different JPEG quality is not a baseline for this decision; that
    is the cover-source-mismatch trap, and it is the single most common way
    a steganalysis result stops being defensible.
    """

    detector: str
    n_clean: int
    n_false_positives: int
    threshold: float
    source_description: str

    @property
    def fpr(self) -> float:
        if self.n_clean == 0:
            return float("nan")
        return self.n_false_positives / self.n_clean

    def describe(self) -> str:
        return (f"{self.detector}: FPR = {self.n_false_positives}/{self.n_clean} "
                f"= {self.fpr:.4f} at threshold {self.threshold:g} "
                f"on {self.source_description}")


@dataclass
class Finding:
    """One reportable observation about one carrier."""

    carrier: str
    level: Evidence
    detector: str
    claim: str
    domain: Optional[str] = None          # spatial / jpeg-dct / container / ...
    algorithm: Optional[str] = None       # lsb-replacement / steghide / ...
    payload: Optional[bytes] = None
    payload_offset: Optional[int] = None
    baseline: Optional[FalsePositiveBaseline] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def assert_reportable(self) -> "Finding":
        """Enforce the ladder.  Returns self so it can be chained."""
        if self.level >= BASELINE_REQUIRED_FROM and self.baseline is None:
            raise UnsupportedVerdict(
                f"{self.carrier}: {self.level.name} claimed by {self.detector} "
                f"without a false-positive baseline. Either measure one on "
                f"same-source clean carriers or downgrade the finding to E1."
            )
        if self.level >= CONFIRMED_FROM and not self.domain:
            raise UnsupportedVerdict(
                f"{self.carrier}: {self.level.name} requires an identified "
                f"embedding domain, but none was recorded."
            )
        if self.level >= Evidence.E4 and self.payload is None:
            raise UnsupportedVerdict(
                f"{self.carrier}: {self.level.name} claims an extracted payload "
                f"but no payload bytes were attached."
            )
        return self

    def render(self) -> str:
        head = f"[{self.level.name} {self.level.label}] {self.carrier} -- {self.claim}"
        lines = [head, f"    detector : {self.detector}"]
        if self.domain:
            lines.append(f"    domain   : {self.domain}")
        if self.algorithm:
            lines.append(f"    algorithm: {self.algorithm}")
        if self.payload_offset is not None:
            lines.append(f"    offset   : {self.payload_offset}")
        if self.payload is not None:
            preview = self.payload[:48]
            lines.append(f"    payload  : {len(self.payload)} bytes, "
                         f"first bytes {preview!r}")
        if self.baseline is not None:
            lines.append(f"    baseline : {self.baseline.describe()}")
        else:
            lines.append("    baseline : NOT MEASURED (finding capped at E1)")
        return "\n".join(lines)


@dataclass
class Report:
    """A set of findings about one carrier, with an overall verdict."""

    carrier: str
    findings: List[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> "Report":
        finding.assert_reportable()
        self.findings.append(finding)
        return self

    @property
    def verdict(self) -> Evidence:
        if not self.findings:
            return Evidence.E0
        return max(f.level for f in self.findings)

    @property
    def confirmed(self) -> bool:
        return self.verdict >= CONFIRMED_FROM

    def render(self) -> str:
        lines = [
            f"=== steganalysis report: {self.carrier} ===",
            f"verdict: {self.verdict.name} ({self.verdict.label})",
            "",
        ]
        if not self.findings:
            lines.append("No findings.")
        for f in self.findings:
            lines.append(f.render())
            lines.append("")
        return "\n".join(lines)


def cap_without_baseline(level: Evidence, baseline: Optional[FalsePositiveBaseline]) -> Evidence:
    """Utility: silently degrade a level when no baseline exists.

    Detectors that run in bulk use this so a missing baseline produces a
    conservative report rather than an exception.  Interactive analysis
    should prefer assert_reportable() and see the failure.
    """
    if baseline is None and level >= BASELINE_REQUIRED_FROM:
        return Evidence.E1
    return level
