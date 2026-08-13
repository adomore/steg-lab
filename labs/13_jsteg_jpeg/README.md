# Lab 13 -- Jsteg in the JPEG DCT domain

| | |
|---|---|
| Domain | jpeg-dct |
| Algorithm | jsteg |
| Detector | `jsteg_pair_chi_square` (windowed) |
| Measured FPR | 0/30 on same-source clean JPEGs |
| Detection | 10/10 at payloads from 200 to 1100 bytes |
| Evidence ceiling | **E4** -- payload recovered byte-exact |

## Why this lab could not exist before

Gap G-14. `decode_scan` has produced DCT coefficients since P0, but nothing
could write modified coefficients back into a valid JPEG, so the JPEG-domain
labs had nothing to detect. `steganalysis.jpeg_encode` closes that: it
rebuilds the entropy stream with Huffman tables derived from the symbols
actually present, and the round trip is verified coefficient-exact.

Rebuilding the tables is not an optimisation. Changing a coefficient can
change its magnitude category, producing a `(run, size)` symbol the source
file's table never contained -- so reusing the original tables fails on
precisely the inputs an embedder creates.

## The first E4 in the statistical domain

Labs 07 and 09 stopped at E3: they confirmed a payload existed and could not
produce it, because the embedding path was keyed.

Jsteg writes sequentially into every coefficient of magnitude greater than
one. The order is fixed by the algorithm, so extraction needs no key. Domain
is statistical, path is deterministic, payload comes out byte-exact.

## Detection: the attack in its original form

A global chi-square fails on a partial payload -- the untouched tail keeps
its natural imbalance and swamps the sum. Westfeld and Pfitzmann's attack
slides a window along Jsteg's own writing order instead, which detects *and*
measures:

| true payload | detected | estimated length |
|---|---|---|
| 200 bytes | 10/10 | 243 |
| 400 bytes | 10/10 | 396 |
| 800 bytes | 10/10 | 793 |
| 1100 bytes | 10/10 | 1152 |

Clean covers: 0 false positives in 30.

## The threshold is measured, not quoted

The textbook figure for "flattened" is a p-value near 1. On this carrier
that would have missed every payload under about 1200 bytes.

Measured instead: over 30 clean covers the maximum window p-value was 0.277
(mean 0.124), while embedded windows sit between 0.5 and 0.99. The operating
point is 0.40 -- above the observed clean ceiling with margin, far below the
embedded range. It is a property of this carrier, and it has to be
re-measured for any other source.

## Two bugs this lab surfaced

**Jsteg skips magnitude, not value.** The P1 embedder excluded coefficients
equal to 0 and 1, letting -1 through. Writing a 0 bit into -1 produces 0,
which removes that coefficient from the extraction path and desynchronises
every bit after it. Extraction failed at byte 1 until this was fixed, in
both the embedder and this lab.

**The negative pairs mirror, they do not shift.** Magnitude 2 pairs with 3,
so -2 pairs with -3. Pairing -2 with -1 puts an untouchable value into the
test: -1 keeps its natural count while -2 is flattened against nothing, and
the statistic reports 0.000 on every window including fully embedded ones.
The detector looked dead until the mirroring was corrected.

Both were found by building the lab, not by reading the code.

## Reproduce

```bash
python3 -m pytest tests/test_labs_d.py -q
python3 scripts/verify-jpeg-encoder.py
```

## What it teaches

A deterministic embedding path is worth more to an analyst than a weak
algorithm is worth to an embedder. Jsteg's skip rule was chosen to avoid
conspicuous changes and it produced both the fingerprint that identifies the
tool and the fixed order that hands over the payload.

---

[Chinese version](README_zh.md)
