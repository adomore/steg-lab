# Lab 01 -- Data appended after the structural end of file

| | |
|---|---|
| Domain | container |
| Algorithm | append-after-terminator |
| Detector | `trailing_data` |
| Measured FPR | 0/100 on same-source clean covers |
| Evidence ceiling | E4 (payload in hand) |

## The trick

PNG stops at `IEND`. JPEG stops at `EOI`. GIF stops at `0x3B`. None of the
three decoders care what follows, so concatenation is a working carrier:

```bash
cat cover.png payload.zip > carrier.png
```

The result opens in every viewer, renders identically, and carries an
arbitrary amount of data.

## Why it survives

Every mainstream decoder is written to be tolerant. A file that is valid up
to its terminator is a valid file; complaining about what comes afterwards
would break more real-world images than it would catch. That tolerance is
deliberate, correct, and permanently exploitable.

## The detection

There is no algorithm here, and that is the lesson. What makes the check
reliable is an accounting discipline:

1. Parse the container structurally.
2. Compute the offset at which it ends.
3. Compare against the file length.
4. Treat every unexplained byte as something that needs a name.

Detectors that reason about pixels never see this at all, because the bytes
are not in the image.

## Reproduce

```bash
python3 -m pytest tests/test_labs_a.py -q
```

## What it teaches

The first question about a carrier is not "what does this look like?" but
"does every byte in this file have a structural reason to exist?". Most of
the A group is that question asked in different containers.

---

[Chinese version](README_zh.md)
