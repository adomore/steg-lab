# Maintainers

How to resume work without re-deriving the conventions.

## Current state

Version `1.0.0`. Seventeen labs, eight theory chapters, eight gates.
<!-- claim:labs=17 -->
<!-- claim:theory_chapters=8 -->

## The green bar

Everything below must pass before anything ships.

```bash
python3 -m pytest tests -q
python3 gates/g0_wardens.py
python3 gates/g1_parsers.py
python3 gates/g2_classical.py
python3 gates/g3_adaptive.py
python3 gates/g4_statistical.py
python3 gates/g5_feature_sets.py
python3 gates/g6_deep_learning.py --n 160 --epochs 18
python3 gates/g7_capstone.py

# Checks that need a real machine (G-8, G-11, G-18, G-21):
python3 scripts/analyst-checks.py

# Which cross-validations would silently skip here?
python3 scripts/check-crossval.py
python3 scripts/verify-jpeg-encoder.py
python3 scripts/check-docs.py   # includes EN/ZH structural lockstep
python3 scripts/difftest.py --n 200
python3 corpus/generate.py --verify
bash scripts/verify-toolchain.sh
```

Rust side:

```bash
cd rust/stegscan && cargo test --offline -q
```

## Conventions

**Lab anatomy.** `labs/NN_name/lab.py` exposes `NAME`, `DOMAIN`,
`ALGORITHM`, `embed(...)`, `detect(data, name, baseline=None)`. `detect`
must accept `baseline=None` and cap findings at E1 in that case. Directory
names start with digits, so labs load by path via `labs.common.load_lab`,
not by import.

**Every detector needs two tests.** One that it fires on its own stego, one
that it stays silent on 100 same-source clean covers. A detector with only
the first test is a detector that says yes to everything.

**Baselines are per-detector, not per-lab.** `measure_baseline` filters by
detector name. Counting every finding in a report conflates a weak heuristic
with a strong one and produces a number that describes neither.

**Baselines are source-matched.** Pass `kinds=` so the clean set comes from
the same image family as the carrier. Skipping this moved lab 07's
false-positive rate from 0% to 25%, which is cover source mismatch and is
not a subtle effect.

**An unvalidated detector does not enter `DETECTORS`.** Two are in the
module, renamed with an `_UNVALIDATED` suffix and documented. A registry
that lists an estimator nobody checked is how an unchecked number reaches a
report.

**Bilingual lockstep from day one.** Every `.md` has a `_zh` sibling with an
identical heading structure. Prose is translated; code, commands, flags,
identifiers and tool names are not. `check-docs.py` enforces all three.

**Gates are the acceptance criteria.** A theory chapter is finished when its
gate passes, not when it reads well. Gates may contain criteria that must
*fail* -- G4 requires RS and SPA to collapse against LSB matching.

**No binaries in the repository.** Corpora are generated from seeds and
pinned by SHA-256.

## Adding a lab NN

1. `mkdir labs/NN_name`, write `lab.py` to the interface above.
2. Add `"NN_name"` to `LAB_DIRS` in `labs/common.py`.
3. Write `README.md` and `README_zh.md` with the summary table at the top,
   including the measured FPR.
4. Add tests to `tests/test_labs_a.py`: detection, payload recovery, and the
   zero-false-positive test.
5. Add a checklist line to both `STEGANALYSIS_CHECKLIST.md` and `_zh`.
6. If the lab changes what the Rust scanner sees, extend
   `scripts/difftest.py`'s anomaly set.
7. Run the green bar.

## Environment notes

- **PEP 668.** Kali 2024.1+ and Debian 12+ reject bare `pip3 install
  --user`. Under `set -e` that kills the whole installer, which is how the
  sibling project's setup script died. `setup-kali.sh` degrades: virtualenv,
  then `--break-system-packages`, then an explicit skip with instructions.
- **Gate dependencies.** G1 needs `pngcheck` and `djpeg` (from
  `libjpeg-progs`); G0 criterion B2 needs `steghide`. All three skip rather
  than fail when absent, which keeps CI honest on minimal images but leaves
  the theory chapters unevidenced.
- **Reference corpora** live outside the repository. Put an archive under
  `corpus/reference/`, run `scripts/register-corpus.py`, then pass
  `--corpus real` to G4 or G5. The loader reads zip members directly, so
  leave a 1.6 GB archive zipped rather than costing 2.6 GB unpacked.
- **rustfmt** was absent from the build environment, so the `cargo fmt` CI
  step is `continue-on-error`. See gap G-5.
- **Rust edition 2021** only, matching the apt-packaged toolchain.

## Roadmap

**P1 -- done.** T2 and T4; LSB-R, LSB-M, Jsteg and F5 from scratch;
chi-square, RS and WS detectors; labs 07 and 08; gates G2 and G4. Two
detectors were written and withheld as unvalidated (gaps G-11, G-12), and
the corpus was shown inadequate for statistical work by measurement rather
than by assumption.

**P2** -- T3 and T5; STC and adaptive costs; SPAM/SRM plus ensemble;
C-group JPEG-domain labs, which reuse `decode_scan`'s coefficient output;
lab 17 connects to stegseek-rs.

**P3** -- T6 and T7; D and E groups; the blind capstone gate G7; filesystem
slack once a real volume is available.

---

[Chinese version](MAINTAINERS_zh.md)
