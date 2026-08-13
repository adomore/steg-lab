# Lab 04 -- PNG chunk anomalies, and the one that hides pixels in plain sight

| | |
|---|---|
| Domain | container |
| Algorithm | private-chunk / stale-crc / header-truncation |
| Detectors | `png_unknown_chunk`, `png_crc_mismatch`, `png_height_truncation` |
| Measured FPR | 0/100 on same-source clean covers |
| Evidence ceiling | E4 for chunk and truncation variants, E2 for stale CRC |

## Three variants, three different failures

**(a) Private chunk.** A structurally perfect chunk with a type nobody
registered. Correct length, valid CRC, correct property bits. Detected only
by asking what each chunk is *for*.

**(b) Stale CRC.** Payload written over existing chunk data without fixing
the checksum. No viewer verifies chunk CRCs, so the image still renders.

**(c) Height truncation.** `IHDR` declares fewer rows than the `IDAT` stream
actually contains. Every viewer renders the declared image and silently
discards the rest.

## Why (c) is the one to internalise

Nothing is appended. Nothing is out of place. Every CRC is valid. The file
is a completely legal PNG that any conformance checker will pass.

The payload is concealed by a *declaration*, not by an encoding. So:

- appended-data checks see nothing (`trailing == b""`)
- CRC verification sees nothing (all valid)
- entropy scanners see nothing (it is ordinary compressed pixel data)
- pixel statistics see nothing (the hidden rows are never decoded)

The only check that finds it is inflating `IDAT` and comparing its length
against what the header implies. The test asserts all of the above
explicitly, so the claim is verified rather than asserted.

## The property-bit trap

PNG encodes four flags in the *case* of the four type letters:

| letter | lowercase means |
|---|---|
| 1 | ancillary |
| 2 | private -- **not letter 3** |
| 3 | must be uppercase (reserved) |
| 4 | safe to copy |

The reference implementation in this repository had letters 2 and 3 swapped
until gate G1 caught it. The same test now lives on both the Python and Rust
sides.

## Reproduce

```bash
python3 -m pytest tests/test_labs_a.py -q
python3 gates/g1_parsers.py
```

## What it teaches

A file can be simultaneously specification-conformant and dishonest.
Conformance checking and steganalysis are different questions.
