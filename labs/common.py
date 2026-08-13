"""Shared harness for the lab modules.

Every lab exposes the same three things:

    NAME, DOMAIN, ALGORITHM   -- taxonomy tags
    embed(cover, payload, **kw) -> bytes
    detect(data, name, baseline=None) -> Report

`detect` must accept `baseline=None` and, in that case, cap its findings at
E1.  That is not politeness; it is the rule from steganalysis.evidence made
mechanical.  A lab that reports E3 without a baseline will raise, and its
test will go red.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, List, Optional

from steganalysis import corpus
from steganalysis.evidence import Evidence, FalsePositiveBaseline, Report

LABS_DIR = Path(__file__).resolve().parent

LAB_DIRS = [
    "01_trailing_data",
    "02_polyglot",
    "03_metadata",
    "04_png_chunks",
    "05_zip_structure",
    "06_jpeg_segments",
    "07_lsb_replacement",
    "08_lsb_matching",
    "09_feature_based",
    "13_jsteg_jpeg",
    "14_f5_calibration",
    "18_audio_lsb",
    "20_text_unicode",
    "21_network",
    "22_video",
    "23_filesystem",
]


def load_lab(dirname: str) -> ModuleType:
    """Import labs/<dirname>/lab.py under a synthetic module name.

    Directory names start with digits, so they cannot be package names.
    Loading by path keeps the numbering (which readers want) without
    fighting Python's identifier rules.
    """
    path = LABS_DIR / dirname / "lab.py"
    modname = f"steglab_lab_{dirname}"
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


def load_all_labs() -> Dict[str, ModuleType]:
    return {d: load_lab(d) for d in LAB_DIRS}


def measure_baseline(
    detect_fn: Callable[..., Report],
    detector_name: str,
    n_clean: int = 100,
    fmt: str = "png",
    seed0: int = 300_000,
    threshold: float = 0.0,
    fire_at: Evidence = Evidence.E1,
    kinds: Optional[list] = None,
) -> FalsePositiveBaseline:
    """Run a detector over n_clean same-source covers and count how often it fires.

    `fire_at` is the level at or above which a report counts as a positive.
    Structural detectors fire at E1 already, so the default is E1: it is the
    strictest reading, and a structural detector that fires on clean covers
    at all is broken.

    The clean set is generated from the same CoverSpec family as the stego
    carriers, which is what makes it a legitimate baseline. Swap in real
    photographs from the same camera for a real case; see T4 on cover-source
    mismatch for why "same" has to be taken literally.
    """
    specs = corpus.baseline_specs(n=n_clean, fmt=fmt, seed0=seed0, kinds=kinds)
    positives = 0
    for spec in specs:
        blob = corpus.render(spec)
        report = detect_fn(blob, spec.name, baseline=None)
        # A baseline belongs to ONE detector, not to a lab. Counting every
        # finding conflates a weak heuristic with a strong one and produces a
        # number that describes neither.
        hits = [f for f in report.findings
                if f.detector == detector_name and f.level >= fire_at]
        if hits:
            positives += 1
    return FalsePositiveBaseline(
        detector=detector_name,
        n_clean=n_clean,
        n_false_positives=positives,
        threshold=threshold,
        source_description=(f"{n_clean} synthetic {fmt.upper()} covers"
                            + (f" [{', '.join(kinds)}]" if kinds else " [mixed]")
                            + f", corpus.baseline_specs(seed0={seed0})"),
    )


def payload_blob(tag: str, size: int = 96) -> bytes:
    """A recognisable payload so a successful extraction is unambiguous."""
    body = f"steg-lab payload [{tag}] ".encode()
    return (body * ((size // len(body)) + 1))[:size]


def summarise(reports: List[Report]) -> str:
    lines = []
    for r in reports:
        lines.append(f"{r.carrier:<28} {r.verdict.name}  {r.verdict.label}")
    return "\n".join(lines)


__all__ = [
    "LAB_DIRS", "load_lab", "load_all_labs", "measure_baseline",
    "payload_blob", "summarise", "Evidence", "Report", "FalsePositiveBaseline",
    "Optional",
]
