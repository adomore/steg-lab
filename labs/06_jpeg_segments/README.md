# Lab 06 -- JPEG segment space, and where byte accounting runs out

| | |
|---|---|
| Domain | container |
| Algorithm | comment-segment / rogue-appn / post-scan-padding |
| Detectors | `jpeg_comment_segment`, `jpeg_rogue_appn`, `jpeg_scan_surplus`, `jpeg_byte_accounting` |
| Measured FPR | 0/100 on same-source clean covers |
| Evidence ceiling | E4 |

## Three variants

**(a) COM segment.** The documented comment slot, skipped by every decoder.

**(b) Rogue APPn.** A marker in a slot no mainstream encoder emits.
Real encoders use `APP0` (JFIF), `APP1` (EXIF/XMP), `APP2` (ICC), `APP13`
(Photoshop IRB) and `APP14` (Adobe). Anything else is worth a look --
especially when it carries a plausible-looking vendor signature, which is
what a competent embedder puts there.

**(c) Post-scan padding.** Bytes between the end of the entropy-coded scan
and `EOI`.

## Where structure alone stops working

Byte accounting -- every byte belongs to a segment, to a scan, or to a
finding -- closes (a) and (b). It does **not** close (c), and finding that
out was the most useful thing in building this lab.

A scan has no declared length. It ends wherever the next marker begins.
Append bytes that contain no `0xFF` and the scan walk simply absorbs them,
because from the outside they are indistinguishable from compressed data.
The first implementation of this detector reported nothing, correctly.

Closing (c) requires decoding the entropy stream and asking where the last
MCU actually finished. That is what `steganalysis.jpeg.decode_scan` does:
a baseline-sequential Huffman decoder that reports `consumed_end` against
`physical_end`. On a clean cover the surplus is exactly zero.

The cost was worth paying twice over -- the same decoder yields the DCT
coefficients that the C-group JPEG-domain labs need.

## The scan-walk trap

Searching for `0xFFD9` to find the end of a JPEG is wrong: compressed data
contains that pair by chance. Inside a scan a literal `0xFF` is stored as
`0xFF 0x00`, and only a non-zero, non-`RSTn` second byte ends the scan. The
test asserts the naive search lands *inside* the scan on the sample, so the
justification is measured rather than argued.

## Reproduce

```bash
python3 -m pytest tests/test_labs_a.py -q
```

## What it teaches

Structural analysis has a floor. When a format declines to declare a length,
you have to decode to find the boundary. This is the last A-group lab for
exactly that reason.

---

[Chinese version](README_zh.md)
