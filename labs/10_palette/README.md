# Lab 10 -- Palette carriers: hiding in an ordering

| | |
|---|---|
| Domain | palette |
| Algorithm | ezstego |
| Detector | `palette_sorted_pair_chi_square` (windowed) |
| Measured FPR | 0/24 on same-source clean palette PNGs |
| Detection | 10/10 at 800 and 1500 bytes; 0/10 at 300 |
| Evidence ceiling | E4 -- the ordering is derivable from the file |

## Two places to hide, one of which does not work

A palette image stores indices, not colours.

**The index LSB** is the obvious target and it is useless. Palette order is
arbitrary -- a quantiser emits colours in whatever order its algorithm reached
them -- so flipping the low bit of an index swaps a pixel for an unrelated
colour. The damage is visible.

**EzStego** stops treating the index as a number and treats it as a position in
a *sorted* order. Sort the palette by luminance and positions 2k and 2k+1 name
colours adjacent in brightness, so moving between them is nearly invisible. The
payload lives in the LSB of the luminance-sorted position.

## The trick is the tell

Sorting by luminance turns the palette into a sequence of near-duplicate pairs,
and embedding equalises the counts within each pair. That is the same structure
the chi-square attack finds in the spatial domain, applied to sorted positions
rather than to pixel values.

A detector working on raw indices sees nothing, because the raw pairs are
meaningless. One that reconstructs the sorted order sees it immediately -- and
it can reconstruct it exactly, because the palette travels inside the file.

## No key is needed, so this reaches E4

Labs 07 and 09 stopped at E3: they confirmed a payload and could not produce
it, because the embedding path was keyed. EzStego's path is not. The ordering
is a function of the palette, the palette is in the file, and the writing order
is sequential. Payload out, byte-exact, 10/10.

## Windowed, for the same reason lab 13 is

A 300-byte payload in a 192x192 carrier touches 6.5% of pixels and does not
move the global statistic at all. Sliding the test along EzStego's own writing
order finds the run of flattened windows at the front:

| payload | detected | estimated |
|---|---|---|
| 300 bytes | 0/10 | -- |
| 800 bytes | 10/10 | 512 |
| 1500 bytes | 10/10 | 1382 |

The 300-byte miss is not a tuning failure. 2400 bits is under two thirds of one
4096-sample window, so no window is ever fully embedded. **The window size is
the detection floor**, and shrinking it trades that floor against the count
noise in each window. Stated rather than hidden.

Clean carriers: peak window p-value 0.0000 across all 24, against 0.60 for the
operating point.

## Reproduce

```bash
python3 -m pytest tests/test_labs_e.py -q
```

## What it teaches

Steganography does not need a numeric value to hide in. It needs any degree of
freedom the format leaves unconstrained, and the order of a palette is one. The
detector's job is to find the frame in which that freedom becomes a statistic --
here, one sort.

---

[Chinese version](README_zh.md)
