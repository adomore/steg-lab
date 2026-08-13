#!/usr/bin/env python3
"""Gate G0 -- the three wardens, made concrete.

Simmons' prisoners' problem defines the adversary by what it is allowed to
do to the channel, not by how clever it is.  T0 claims three warden classes
matter operationally.  This gate refuses to let that stay an assertion.

Criteria (all three must hold):

  A. PASSIVE warden.  Observes only.  The payload must survive byte-identically
     (BER == 0) across the channel, so the warden's only possible move is
     detection.  Anything else and we would be describing a different warden.

  B. ACTIVE warden.  Recompresses at JPEG q=90 without knowing whether a
     payload exists.  Two sub-criteria:
       B1. Sequential LSB payload: bit error rate > 0.45 after recompression
           (i.e. the recovered bits are indistinguishable from coin flips).
       B2. steghide payload: extraction failure rate == 100% over N trials.
     Note the asymmetry these two numbers expose -- see the discussion at
     the bottom of docs/theory/T0_threat_model.md.

  C. MALICIOUS warden.  Substitutes its own payload and forwards.  The
     receiver must extract the *forged* message with no indication of
     tampering, demonstrating that steganography without authentication
     provides no integrity whatsoever.

Run:  python3 gates/g0_wardens.py
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from steganalysis import corpus, container  # noqa: E402

N_TRIALS = 12
PAYLOAD_LEN = 256
RECOMPRESS_QUALITY = 90
BER_THRESHOLD = 0.45
RESULTS = Path(__file__).resolve().parent / "results"


def _cover_array(seed: int) -> np.ndarray:
    spec = corpus.CoverSpec(name="g0.png", seed=seed, width=256, height=192,
                            kind="photo_like", fmt="png")
    return np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("RGB"))


def _recompress(arr: np.ndarray, quality: int) -> np.ndarray:
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="JPEG", quality=quality, subsampling=0)
    buf.seek(0)
    return np.array(Image.open(buf).convert("RGB"))


def criterion_a_passive() -> dict:
    """Lossless channel: the payload arrives intact, so detection is the game."""
    rng = np.random.default_rng(7)
    bers = []
    for t in range(N_TRIALS):
        cover = _cover_array(3000 + t)
        payload = rng.integers(0, 256, PAYLOAD_LEN, dtype=np.uint8).tobytes()
        stego = container.lsb_replace(cover, payload)
        # The passive warden forwards the PNG untouched; round-trip through
        # a real PNG encode/decode to prove losslessness is not assumed.
        buf = io.BytesIO()
        Image.fromarray(stego, mode="RGB").save(buf, format="PNG")
        buf.seek(0)
        received = np.array(Image.open(buf).convert("RGB"))
        got = container.lsb_extract(received, PAYLOAD_LEN)
        bers.append(container.bit_error_rate(payload, got))
    worst = max(bers)
    return {
        "name": "A_passive_channel_is_lossless",
        "trials": N_TRIALS,
        "max_ber": worst,
        "pass": worst == 0.0,
        "note": "BER must be exactly 0; the passive warden cannot alter the carrier.",
    }


def criterion_b1_active_lsb() -> dict:
    """Active warden recompresses; sequential LSB payload should be destroyed."""
    rng = np.random.default_rng(11)
    bers = []
    for t in range(N_TRIALS):
        cover = _cover_array(4000 + t)
        payload = rng.integers(0, 256, PAYLOAD_LEN, dtype=np.uint8).tobytes()
        stego = container.lsb_replace(cover, payload)
        laundered = _recompress(stego, RECOMPRESS_QUALITY)
        got = container.lsb_extract(laundered, PAYLOAD_LEN)
        bers.append(container.bit_error_rate(payload, got))
    median = float(np.median(bers))
    return {
        "name": "B1_active_warden_destroys_lsb",
        "trials": N_TRIALS,
        "quality": RECOMPRESS_QUALITY,
        "median_ber": median,
        "min_ber": float(np.min(bers)),
        "max_ber": float(np.max(bers)),
        "threshold": BER_THRESHOLD,
        "pass": median > BER_THRESHOLD,
        "note": "BER near 0.5 means the recovered bits carry no information.",
    }


def criterion_b2_active_steghide() -> dict:
    """Active warden vs steghide.  Requires the steghide binary."""
    if shutil.which("steghide") is None:
        return {
            "name": "B2_active_warden_defeats_steghide",
            "pass": None,
            "skipped": "steghide not installed; run scripts/setup-kali.sh",
        }

    failures = 0
    survived = 0
    errors = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for t in range(N_TRIALS):
            cover_bytes = corpus.render(corpus.CoverSpec(
                name="c.jpg", seed=5000 + t, width=256, height=192,
                kind="photo_like", fmt="jpeg", quality=95))
            cover = tmp / f"cover{t}.jpg"
            cover.write_bytes(cover_bytes)
            secret = tmp / f"secret{t}.txt"
            secret.write_bytes(b"G0 active warden trial %d\n" % t)
            stego = tmp / f"stego{t}.jpg"

            emb = subprocess.run(
                ["steghide", "embed", "-cf", str(cover), "-ef", str(secret),
                 "-sf", str(stego), "-p", "gate0", "-q", "-f"],
                capture_output=True)
            if emb.returncode != 0 or not stego.exists():
                errors.append(f"trial {t}: embed failed: {emb.stderr.decode()[:120]}")
                continue

            # Sanity: without the warden, extraction must succeed.  A gate that
            # only shows failure proves nothing about the warden.
            out_ok = tmp / f"ok{t}.txt"
            ext_ok = subprocess.run(
                ["steghide", "extract", "-sf", str(stego), "-xf", str(out_ok),
                 "-p", "gate0", "-q", "-f"], capture_output=True)
            if ext_ok.returncode != 0:
                errors.append(f"trial {t}: control extraction failed, gate is invalid")
                continue

            # The warden decodes and re-encodes at q=90.
            arr = np.array(Image.open(stego).convert("RGB"))
            laundered = tmp / f"laundered{t}.jpg"
            Image.fromarray(arr).save(laundered, format="JPEG",
                                      quality=RECOMPRESS_QUALITY, subsampling=0)

            out = tmp / f"out{t}.txt"
            ext = subprocess.run(
                ["steghide", "extract", "-sf", str(laundered), "-xf", str(out),
                 "-p", "gate0", "-q", "-f"], capture_output=True)
            if ext.returncode != 0:
                failures += 1
            elif out.exists() and out.read_bytes() == secret.read_bytes():
                survived += 1
            else:
                failures += 1

    attempted = failures + survived
    return {
        "name": "B2_active_warden_defeats_steghide",
        "trials": attempted,
        "extraction_failures": failures,
        "payload_survived": survived,
        "failure_rate": (failures / attempted) if attempted else float("nan"),
        "errors": errors,
        "pass": attempted > 0 and failures == attempted,
        "note": "steghide has no error correction; any DCT change breaks it.",
    }


def criterion_c_malicious() -> dict:
    """Malicious warden replaces the payload; the receiver cannot tell."""
    rng = np.random.default_rng(13)
    forged_ok = 0
    for t in range(N_TRIALS):
        cover = _cover_array(6000 + t)
        real = rng.integers(0, 256, PAYLOAD_LEN, dtype=np.uint8).tobytes()
        forgery = b"MEET AT NOON INSTEAD -- warden".ljust(PAYLOAD_LEN, b"\x00")
        stego = container.lsb_replace(cover, real)
        # The warden knows the channel convention but not the sender's intent.
        tampered = container.lsb_replace(stego, forgery)
        received = container.lsb_extract(tampered, PAYLOAD_LEN)
        if received == forgery:
            forged_ok += 1
    return {
        "name": "C_malicious_warden_substitutes_payload",
        "trials": N_TRIALS,
        "forgeries_accepted": forged_ok,
        "pass": forged_ok == N_TRIALS,
        "note": ("Steganography hides existence, not integrity. Confidentiality "
                 "and authentication must come from the payload's own crypto."),
    }


def main() -> int:
    results = [
        criterion_a_passive(),
        criterion_b1_active_lsb(),
        criterion_b2_active_steghide(),
        criterion_c_malicious(),
    ]

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "G0.json").write_text(json.dumps(results, indent=2) + "\n")

    print("=" * 70)
    print("Gate G0 -- warden model")
    print("=" * 70)
    hard_fail = False
    for r in results:
        status = "SKIP" if r.get("pass") is None else ("PASS" if r["pass"] else "FAIL")
        if status == "FAIL":
            hard_fail = True
        print(f"[{status}] {r['name']}")
        for k, v in r.items():
            if k in ("name", "pass", "note"):
                continue
            print(f"        {k}: {v}")
        if "note" in r:
            print(f"        -> {r['note']}")
    print("=" * 70)
    print("GATE G0:", "FAIL" if hard_fail else "PASS")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
