# Analyst checklist

Work top to bottom; each section cites the lab or chapter that explains why
the step is there. It stopped fitting on one page when the repository grew
past the container labs, and a checklist that leaves out five carrier
families to stay short is the wrong trade: absent coverage is not absent
risk, and that applies to this document too.

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

## 2. Signal-layer triage -- images

- [ ] Relative payload, not absolute size: bpp or bpnzac. (T1 1.4)
- [ ] Known-tool signatures before generic statistics -- they are cheaper
      and give an algorithm family, which is E3.
- [ ] Bit-plane inspection: does the LSB plane look like noise or like
      structure?
- [ ] LSB replacement: Weighted Stego and RS estimate the payload, not only
      its presence. Both need a same-source baseline -- an unmatched one took
      this lab's false-positive rate from 0% to 25%. (lab 07)
- [ ] LSB matching: the structural estimators collapse to chance here, and
      that is the expected result rather than a broken run. (lab 08)
- [ ] When no estimator applies, a trained feature set still does. SPAM686
      plus an ensemble is embedder-agnostic, and it needs training data from
      this source: under cover source mismatch it returns to chance. (lab 09)
- [ ] Palette images: sort the palette and test adjacent pairs, measured
      along the embedding order rather than over the whole image. (lab 10)
- [ ] JPEG: quantisation table fingerprint, marker layout, double-compression
      evidence.
- [ ] JPEG-DCT, sequential embedding: slide the chi-square along the writing
      order. A global test is swamped by the untouched tail. (lab 13)
- [ ] JPEG-DCT, shrinkage-aware embedding: calibrate by cropping and
      recompressing, and compare against a source model built from clean
      same-source carriers rather than from the carrier itself. (lab 14)

## 3. Signal-layer triage -- everything that is not an image

The image carriers get the most attention and are not the most common.

- [ ] Audio: bit depth decides whether the statistics have any power at all.
      An 8-bit carrier gives a 20x response, a 16-bit one is inert. Look for
      near-silence rather than silence, and require the deviations to be
      one-sided. (lab 18)
- [ ] Text: zero-width characters, variation selectors, trailing whitespace.
      Test script context, not run length -- an adversary who spreads the
      payload defeats run length and walks straight into context. (lab 20)
- [ ] Network: header fields, DNS labels, inter-packet timing. A randomising
      network stack is indistinguishable from an IP-ID channel, so that check
      caps at E1 by design and says so. (lab 21)
- [ ] Video: compare frame pairs along the temporal axis. Re-encoding
      destroys the payload and the signal together, so a transcoded capture
      answers nothing about the original. (lab 22)
- [ ] Filesystem: file slack and alternate data streams. Non-zero slack has a
      second and entirely normal explanation -- a deleted file's tail -- and
      no statistic separates it from a payload. Report both readings and let
      the analyst read the recovered bytes. (lab 23)

## 4. Before writing any verdict

- [ ] Is there a **measured** false-positive rate on same-source clean
      carriers? If not, cap the finding at E1. No exceptions.
- [ ] Is the embedding domain identified? Required for E3.
- [ ] Are the payload bytes in hand? Required for E4.
- [ ] Is the extraction reproducible from a recorded key? Required for E5.
- [ ] Could normal processing produce this? Resizing, re-encoding, platform
      transcoding and metadata stripping all leave artefacts that look like
      embedding.

## 5. Report language

- [ ] State the level, the detector, the threshold and the baseline together.
      A number without its baseline is not a result.
- [ ] Distinguish "no payload found" from "no payload present". An active
      channel may have destroyed one. (T0 0.6)
- [ ] Record what was **not** tested. Absent coverage is not absent risk.

## The rule, restated

> No extraction and no baseline, no verdict.

---

[Chinese version](STEGANALYSIS_CHECKLIST_zh.md)
