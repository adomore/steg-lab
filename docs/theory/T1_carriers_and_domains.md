# T1 -- Carriers and embedding domains

> Gate: **G1** -- `python3 gates/g1_parsers.py` -- PASSED

## 1.1 Where a payload can live

Every carrier offers three distinct kinds of room, and they need different
tools:

| Layer | Room comes from | Detected by | Labs |
|---|---|---|---|
| Container | syntax the decoder ignores | structural accounting | A group (01-06) |
| Signal | perceptual redundancy in the samples | statistics | B, C, D groups |
| Semantic | choices the format leaves free | modelling the encoder | C group, T5 |

The container layer is where this course starts, for two reasons. It is
where most real-world steganography actually lives -- malware droppers and
CTF puzzles alike -- and it is where the reasoning is deterministic, so an
analyst can build the accounting habit before facing statistics.

## 1.2 The container layer, format by format

**PNG** is a chunk stream: `length | type | data | crc`. Four property bits
live in the *case* of the four type letters, and the ordering catches people
out:

| letter | lowercase means |
|---|---|
| 1 | ancillary -- a decoder may skip it |
| 2 | private -- not in the registry |
| 3 | must be **uppercase** (reserved) |
| 4 | safe to copy across unrelated edits |

The private bit is letter 2, not letter 3. This repository's own parser had
it wrong until gate G1's offset check failed on a chunk that was correctly
located but incorrectly classified.

Room in PNG: unknown chunk types, oversized text chunks, stale CRCs, data
after `IEND`, and an `IHDR` that declares fewer rows than `IDAT` contains.

**JPEG** is a marker stream. Segments carry a two-byte length; the
entropy-coded scan does not. Inside a scan a literal `0xFF` is stored as
`0xFF 0x00`, and only a non-zero, non-`RSTn` second byte terminates it.

That missing length field is the important asymmetry. It is why byte
accounting -- otherwise the workhorse of this layer -- cannot detect padding
appended to a scan, and why lab 06 needs a Huffman decoder rather than a
parser. Section 1.5 develops this.

Room in JPEG: `COM` segments, unusual `APPn` slots, data after `EOI`, and
post-scan padding.

**ZIP** is read backwards from the end-of-central-directory record, so
anything the central directory declines to mention is invisible by design.
Room: the archive comment, gaps between entries, extra fields, and the
general-purpose flag bit that claims encryption without providing any.

## 1.3 The signal layer, in one page

Detail belongs to T2-T6; the map belongs here.

**Spatial domain.** Pixel values, usually 8-bit. LSB replacement writes the
bit directly; LSB matching adds or subtracts one. These sound similar and
are not: replacement introduces a structural asymmetry between even and odd
values that RS analysis and Sample Pair Analysis exploit, while matching
does not, which is why those detectors collapse against it. T4 measures that
collapse rather than describing it.

**JPEG DCT domain.** Quantised coefficients, not pixels. Jsteg, OutGuess, F5
and steghide all live here, and each leaves a different fingerprint:
histogram shape, quantisation table choice, marker layout. The quantisation
table alone is often enough to identify the producing software.

**Palette.** GIF and 8-bit PNG. The payload can go into pixel indices or
into the palette's ordering, which is what EzStego does.

**Audio, video, text, network.** WAV LSB and echo hiding; motion vectors and
container attachments; zero-width characters and variation selectors; header
fields, DNS labels and inter-packet timing. D group, in P3.

## 1.4 The one number that organises everything: bits per element

Payload size alone says nothing. The comparable quantity is **relative
payload**, in bits per pixel (bpp) for the spatial domain or bits per
non-zero AC coefficient (bpnzac) for JPEG.

This matters because detector performance is a function of relative payload,
not absolute size. The same 10 KB payload is trivially detectable in a
128x128 cover and close to invisible in a 24-megapixel one. Every ROC curve
in T4 and T5 is plotted against this axis, and a result quoted without it is
not a result.

## 1.5 Gate G1: parsing without a decoder

The claim is that a carrier's structure can be recovered from the byte
stream alone. The risk in that claim is self-deception: it is easy to write
a parser that agrees with your own mental model and disagrees with reality.
So the gate scores the hand-written parsers against two implementations that
were not written for this repository.

### Criterion A -- PNG versus pngcheck

50 covers, **162 chunks compared**, zero tolerance for disagreement on
chunk type, file offset or declared length, plus dimensions, bit depth and
interlace flag.

**Mismatches: 0.**

One detail worth recording because it wastes an afternoon otherwise:
`pngcheck` reports the offset of the four-byte *type* field, while this
parser reports the offset of the *length* field that precedes it. The
mapping is `pngcheck_offset = parser_offset + 4`.

### Criterion B -- JPEG versus djpeg

50 covers across five quality factors, **100 quantisation tables compared**
after de-zigzagging into natural order, plus frame dimensions and component
count.

**Mismatches: 0.**

libjpeg stores quantisation tables in natural raster order after
`jpeg_read_header`, while the `DQT` segment stores them in zig-zag order.
Comparing them without applying `jpeg_natural_order` produces 64 spurious
differences per table and a very confusing hour.

### Criterion C -- offset localisation

Three carriers with payloads at known offsets: appended after `IEND`, a
private `stEG` chunk before `IEND`, and a `COM` segment after `SOI`. Each
offset must be reported exactly, and every byte of each file must be
accounted for.

**All three pass** -- but only after the property-bit bug in section 1.2 was
fixed. The gate found a real defect in the code it was written to validate,
which is the best possible argument for having it.

## 1.6 The habit this chapter is really teaching

Three questions, asked in order, before any statistics:

1. **Does the container parse?** Errors are findings, not exceptions.
2. **Does every byte belong to something?** Sum the structures and compare
   against the file length.
3. **Do the format's two descriptions of itself agree?** Local header versus
   central directory; `IHDR` versus inflated `IDAT`; declared scan versus
   decoded scan.

Question 3 is the general form of most of the A group, and it keeps working
at higher layers.

## 1.7 Further reading

The PNG specification (ISO/IEC 15948) and ITU-T T.81 for JPEG, both worth
reading in the original. `pngcheck` and libjpeg's `djpeg` sources are the
reference implementations this chapter is scored against. Fridrich (2009)
chapter 4 for the signal-layer map.

---

Previous: [T0 -- Problem definition and threat model](T0_threat_model.md) |
[Chinese version](T1_carriers_and_domains_zh.md)
