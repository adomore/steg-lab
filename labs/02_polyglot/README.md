# Lab 02 -- Polyglots: two parsers, one file, both correct

| | |
|---|---|
| Domain | container |
| Algorithm | format-polyglot |
| Detectors | `polyglot_zip` (structural), `polyglot_signature_scan` (weak) |
| Measured FPR | `polyglot_zip` 0/500; `polyglot_signature_scan` 2/500 |
| Evidence ceiling | E4 structural, E1 signature-only |

## The trick

A polyglot hides an *interpretation*, not bytes. PNG reads forwards from a
magic number; ZIP reads backwards from the end-of-central-directory record.
They never contend for the same bytes, so one file can be both.

This lab also rebases the archive's internal offsets after prefixing. A
naively appended ZIP still opens, but the reader prints a warning about
extra leading bytes. Analysts learn to trust warnings; a polyglot built by
someone competent does not produce one.

## Why "it renders as an image" proves nothing

Rendering exercises one parser. An extension allowlist checks one parser's
opinion. The useful question is not "what is this file?" but "how many valid
answers does that question have?".

## The detection

Two detectors, deliberately unequal:

- `polyglot_zip` opens the file with a real archive reader and verifies
  every entry. Structural, decisive, E4.
- `polyglot_signature_scan` looks for embedded magic bytes. Cheap, and
  wrong often enough to matter.

## The measured result that matters

Over 500 clean synthetic PNGs the signature scan fired twice. Compressed
pixel data contains arbitrary byte sequences, so `PK\x03\x04` turns up by
chance. That is 0.4% -- small, but on a million-file corpus it is four
thousand files an analyst must dismiss by hand.

This is exactly why E1 exists, and why the test asserts the weak detector
*does* misfire. If that number ever reaches zero, the clean set is too small
to make the point, not the detector improved.

## Reproduce

```bash
python3 -m pytest tests/test_labs_a.py -q
```

## What it teaches

A signature hit is a lead. A structure that parses is a finding. The
evidence ladder makes the difference recordable instead of rhetorical.

---

[Chinese version](README_zh.md)
