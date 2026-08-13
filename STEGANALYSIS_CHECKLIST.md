# Analyst checklist

One page. Work top to bottom; each section cites the lab or chapter that
explains why the step is there.

## 0. Before touching the artefact

- [ ] Hash it. Work on a copy. Record where it came from and how.
- [ ] Establish the **source**: device, software, processing chain, platform
      it transited. Every threshold later depends on this. (T1 1.4)
- [ ] Obtain clean carriers **from that same source** for a baseline. If you
      cannot, say so in the report; the ceiling drops to E1. (T0 0.3)
- [ ] Decide which warden you are: analysing, or destroying? They are
      incompatible. (T0 0.6)

Tool-specific traps -- exit codes that do not mean what they look like, tools
that cannot report their own blind spots -- are in
[Tool practice](docs/TOOL_PRACTICE.md).

## 1. Structural accounting -- deterministic, do this first

- [ ] Does the container parse? Errors are findings. (lab 01)
- [ ] Does every byte belong to a structure? Compare the sum against the
      file length. (labs 01, 06)
- [ ] Data after the terminator -- `IEND`, `EOI`, GIF `0x3B`? (lab 01)
- [ ] Does the file open as a second format? (lab 02)
- [ ] Unknown or private chunks; correct property bits; valid CRCs? (lab 04)
- [ ] Does the header agree with the data? Declared height versus inflated
      `IDAT`; declared scan versus decoded scan. (labs 04, 06)
- [ ] Metadata fields longer, denser or more base64-shaped than this source
      normally produces? (lab 03)
- [ ] Archive: encryption flag versus actual decompressibility; comment;
      gaps; local header versus central directory. (lab 05)

## 2. Signal-layer triage

- [ ] Relative payload, not absolute size: bpp or bpnzac. (T1 1.4)
- [ ] Bit-plane inspection: does the LSB plane look like noise or like
      structure?
- [ ] JPEG: quantisation table fingerprint, marker layout, double-compression
      evidence.
- [ ] Known-tool signatures before generic statistics -- they are cheaper
      and give an algorithm family, which is E3.

## 3. Before writing any verdict

- [ ] Is there a **measured** false-positive rate on same-source clean
      carriers? If not, cap the finding at E1. No exceptions.
- [ ] Is the embedding domain identified? Required for E3.
- [ ] Are the payload bytes in hand? Required for E4.
- [ ] Is the extraction reproducible from a recorded key? Required for E5.
- [ ] Could normal processing produce this? Resizing, re-encoding, platform
      transcoding and metadata stripping all leave artefacts that look like
      embedding.

## 4. Report language

- [ ] State the level, the detector, the threshold and the baseline together.
      A number without its baseline is not a result.
- [ ] Distinguish "no payload found" from "no payload present". An active
      channel may have destroyed one. (T0 0.6)
- [ ] Record what was **not** tested. Absent coverage is not absent risk.

## The rule, restated

> No extraction and no baseline, no verdict.

---

[Chinese version](STEGANALYSIS_CHECKLIST_zh.md)
