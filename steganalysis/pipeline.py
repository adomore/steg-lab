"""The analyst's workflow, made executable.

T7's subject is the order in which questions get asked, and the discipline of
not answering one before its prerequisites are met. This module is that order
written down so it can be run on a carrier nobody has told it about.

The sequence follows STEGANALYSIS_CHECKLIST.md:

  1. Structural accounting first, because it is deterministic. Either every
     byte has a reason to exist or it does not; nothing here needs a
     threshold.
  2. Then statistical estimation, which needs thresholds, which need
     baselines.
  3. Baselines are measured on same-source clean carriers before any verdict
     is recorded, not after.

The pipeline receives bytes and a name. It never receives ground truth. That
is enforced by the interface rather than by care, because gate G7 grades it on
carriers whose answers are sealed, and an interface that *can* leak the answer
eventually will.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labs.common import load_lab
from steganalysis.evidence import (Evidence, FalsePositiveBaseline, Finding,
                                   Report)

#: Detector stages in the order the checklist asks for them. Structural labs
#: run first: they are cheap, deterministic, and when they hit they produce a
#: payload rather than a probability.
STRUCTURAL_LABS = [
    "01_trailing_data",
    "02_polyglot",
    "03_metadata",
    "04_png_chunks",
    "05_zip_structure",
    "06_jpeg_segments",
]

#: Statistical labs. These need a threshold and therefore a baseline.
STATISTICAL_LABS = [
    "07_lsb_replacement",
    "09_feature_based",
    "10_palette",
    "13_jsteg_jpeg",
    "14_f5_calibration",
    "18_audio_lsb",
    "20_text_unicode",
    "21_network",
    "22_video",
    "23_filesystem",
]

ALL_LABS = STRUCTURAL_LABS + STATISTICAL_LABS

#: Two labs are deliberately absent from the lists above, and saying so here is
#: the point: an unexplained gap in a registry reads as an oversight, and the
#: next person to notice it has to re-derive the reason or "fix" it.
#:
#:   08_lsb_matching  -- its detect() returns an empty report by construction.
#:                       The lab's content IS that no shipped detector separates
#:                       LSB matching from clean covers, so a pipeline stage for
#:                       it could only ever add cost.
#:   09_feature_based -- its detect() needs a trained FldEnsemble passed in, and
#:                       a blind pipeline has no training set to give it. It
#:                       stays in ALL_LABS, which measure_baselines() iterates,
#:                       but out of CONTAINER_LABS, which routes carriers.
#:
#: tests/test_labs_b.py pins both, so a lab forgotten in future goes red while
#: these two stay stated exceptions.
UNROUTED_BY_DESIGN = {"08_lsb_matching", "09_feature_based"}

#: Which labs apply to which container, and for the statistical ones, to which
#: *kind* of container.
#:
#: This dispatch is not an optimisation. Gate G7 failed its no-over-claims
#: criterion on three of seven clean carriers because every statistical
#: detector ran on every carrier: lab 14's operating point was measured on
#: grayscale JPEGs at quality 90 and was being applied to PNGs and colour
#: JPEGs, lab 07's was measured on grayscale PNGs. A threshold is a property of
#: the carrier -- T4 section 4.7 and T5 section 5.6 both measure what happens
#: when that is ignored -- and a pipeline that applies one across carrier types
#: is committing the same error it teaches analysts to avoid.
CONTAINER_LABS: Dict[str, List[str]] = {
    "png": ["01_trailing_data", "02_polyglot", "03_metadata", "04_png_chunks",
            "07_lsb_replacement", "10_palette"],
    "jpeg": ["01_trailing_data", "03_metadata", "06_jpeg_segments",
             "13_jsteg_jpeg", "14_f5_calibration"],
    "zip": ["02_polyglot", "05_zip_structure"],
    "wav": ["01_trailing_data", "18_audio_lsb"],
    "avi": ["01_trailing_data", "22_video"],
    "pcap": ["21_network"],
    "text": ["20_text_unicode"],
    "volume": ["23_filesystem"],
}

#: Labs whose thresholds were calibrated on single-component (grayscale)
#: carriers and must not be applied to colour ones.
GRAYSCALE_ONLY = {"07_lsb_replacement", "14_f5_calibration"}


def container_kind(data: bytes) -> str:
    """Identify the carrier by its own bytes, never by a filename.

    Order matters in two places. NTFS is tested before FAT because an NTFS boot
    sector also ends in 0x55AA -- it has to, to be bootable -- and AVI is
    tested before WAV because both are RIFF and differ only in the form type.
    Getting either backwards produces a parse that looks plausible and reads
    every field at the wrong offset.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "zip"
    if data[:4] == b"RIFF" and len(data) >= 12:
        form = data[8:12]
        if form == b"AVI ":
            return "avi"
        if form == b"WAVE":
            return "wav"
    if data[:4] in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        return "pcap"
    if len(data) >= 512 and data[3:11] == b"NTFS    ":
        return "volume"
    if len(data) >= 2048 and data[1024 + 56:1024 + 58] == b"\x53\xef":
        return "volume"
    if len(data) >= 512 and data[510:512] == b"\x55\xaa":
        return "volume"
    if _looks_like_text(data):
        return "text"
    return "unknown"


def _looks_like_text(data: bytes, sample: int = 4096) -> bool:
    """Decodable as UTF-8 and made of characters a document would contain.

    The test is by Unicode CATEGORY, not by `str.isprintable()`. Zero-width
    characters are category Cf and report False for isprintable, so a
    printable-ratio test rejects exactly the documents lab 20 exists to
    examine: a text carrier holding a zero-width payload measured 0.64
    printable and was classified as an unknown binary, which routed it away
    from the only lab that could have found it.

    Cf (format) and Mn (non-spacing marks, which include variation selectors)
    are therefore counted as text. Control characters other than the usual
    whitespace are not.
    """
    if not data:
        return False
    try:
        head = data[:sample].decode("utf-8")
    except UnicodeDecodeError:
        return False

    import unicodedata
    ok = 0
    for ch in head:
        if ch in "\n\r\t":
            ok += 1
            continue
        category = unicodedata.category(ch)
        if category[0] in "LNPSZM" or category == "Cf":
            ok += 1
    return ok / len(head) > 0.95


def is_single_component(data: bytes) -> bool:
    """True for grayscale carriers, by structure rather than by filename."""
    kind = container_kind(data)
    if kind == "png":
        from steganalysis import png as png_mod
        parsed = png_mod.parse_png(data)
        return bool(parsed.ihdr and parsed.ihdr.color_type in (0, 4))
    if kind == "jpeg":
        from steganalysis import jpeg as jpeg_mod
        parsed = jpeg_mod.parse_jpeg(data)
        sofs = [s for s in parsed.segments if s.name.startswith("SOF")]
        return bool(sofs and len(sofs[0].data) > 5 and sofs[0].data[5] == 1)
    return False


def applicable_labs(data: bytes) -> List[str]:
    """The labs whose assumptions this carrier actually satisfies."""
    labs = list(CONTAINER_LABS.get(container_kind(data), STRUCTURAL_LABS))
    if not is_single_component(data):
        labs = [lab for lab in labs if lab not in GRAYSCALE_ONLY]
    return labs


@dataclass
class Analysis:
    """One carrier's full pipeline result."""

    carrier: str
    report: Report
    stages_run: List[str] = field(default_factory=list)
    stages_failed: Dict[str, str] = field(default_factory=dict)

    @property
    def verdict(self) -> Evidence:
        return self.report.verdict

    @property
    def domains(self) -> List[str]:
        return sorted({f.domain for f in self.report.findings if f.domain})

    @property
    def algorithms(self) -> List[str]:
        return sorted({f.algorithm for f in self.report.findings if f.algorithm})

    def strongest(self) -> Optional[Finding]:
        if not self.report.findings:
            return None
        return max(self.report.findings, key=lambda f: f.level)


def _detect_one(lab_name: str, data: bytes, name: str,
                baseline: Optional[FalsePositiveBaseline]) -> Optional[Report]:
    lab = load_lab(lab_name)
    return lab.detect(data, name, baseline=baseline)


def analyse(data: bytes, name: str = "<carrier>",
            baselines: Optional[Dict[str, FalsePositiveBaseline]] = None,
            labs: Optional[Sequence[str]] = None) -> Analysis:
    """Run every stage and merge what they find.

    A stage that raises is recorded as a failed stage rather than aborting the
    analysis: a carrier that breaks one parser is exactly the carrier the other
    parsers should still get a look at. But the failure is reported, because
    "the JPEG stage crashed" and "the JPEG stage found nothing" are different
    facts and a report that conflates them is misleading.
    """
    baselines = baselines or {}
    if labs is None:
        labs = applicable_labs(data)
    result = Analysis(carrier=name, report=Report(carrier=name))

    for lab_name in labs:
        try:
            lab = load_lab(lab_name)
            # Baselines are keyed by lab. A missing one caps that lab's
            # findings at E1 by construction, which is the point: the ladder
            # does the enforcing, not the caller's diligence.
            sub = lab.detect(data, name, baseline=baselines.get(lab_name))
            result.stages_run.append(lab_name)
            for finding in sub.findings:
                result.report.findings.append(finding)
        except Exception as exc:                      # noqa: BLE001
            result.stages_failed[lab_name] = f"{type(exc).__name__}: {exc}"

    return result


def measure_baselines(clean: Sequence[bytes],
                      labs: Sequence[str] = tuple(ALL_LABS),
                      source_description: str = "same-source clean carriers"
                      ) -> Dict[str, FalsePositiveBaseline]:
    """Run the pipeline over clean carriers and count what fires.

    This is the step the evidence ladder exists to force. Without it every
    finding is capped at E1, which is the correct behaviour and also a useless
    report -- so the pipeline makes measuring the baseline the price of
    admission rather than an optional extra.
    """
    counts: Dict[str, int] = {lab: 0 for lab in labs}
    seen: Dict[str, int] = {lab: 0 for lab in labs}
    for i, blob in enumerate(clean):
        for lab in applicable_labs(blob):
            if lab not in counts:
                continue
            seen[lab] += 1
            try:
                sub = load_lab(lab).detect(blob, f"clean_{i:03d}", baseline=None)
            except Exception:                          # noqa: BLE001
                continue
            if sub.verdict >= Evidence.E1:
                counts[lab] += 1

    return {
        lab: FalsePositiveBaseline(detector=lab,
                                   n_clean=max(seen[lab], 1),
                                   n_false_positives=counts[lab],
                                   threshold=0.0,
                                   source_description=source_description)
        for lab in labs
    }


def render(result: Analysis) -> str:
    """A report an analyst could hand over."""
    lines = [
        f"=== steganalysis report: {result.carrier} ===",
        f"verdict : {result.verdict.name} ({result.verdict.label})",
        f"stages  : {len(result.stages_run)} run, {len(result.stages_failed)} failed",
    ]
    if result.domains:
        lines.append(f"domain  : {', '.join(result.domains)}")
    if result.algorithms:
        lines.append(f"family  : {', '.join(result.algorithms)}")
    lines.append("")
    if not result.report.findings:
        lines.append("No findings. Note this is not the same as 'no payload "
                     "present': see T0 section 0.6 on active channels.")
    for finding in sorted(result.report.findings, key=lambda f: -f.level):
        lines.append(finding.render())
        lines.append("")
    for lab, err in result.stages_failed.items():
        lines.append(f"[stage failed] {lab}: {err}")
    return "\n".join(lines)
