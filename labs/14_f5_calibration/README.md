# Lab 14 -- F5 detection by calibration

| | |
|---|---|
| Domain | jpeg-dct |
| Algorithm | f5-family |
| Detector | `f5_calibration` |
| Measured FPR | 0/24 on same-source clean grayscale JPEGs |
| Detection | 12/12 at 0.10 and 0.15 bpp, 5/12 at 0.05 |
| Evidence ceiling | E3 |

## Calibration

A histogram attack on JPEG needs a cover histogram to compare against, and
you do not have one. Calibration manufactures an estimate: decompress to
pixels, **crop by four**, recompress with the *same* quantisation table. The
8x8 grid no longer lines up with the original blocks, so the DCT decomposition
is nearly independent of the one that carried the payload, while the content is
almost unchanged.

Carrying the quantisation table across exactly is not optional. Recompressing
at a nominal "same quality" changes the table and then compares two different
quantisers, which yields a confident number about nothing.

## The estimator, and its bias

F5 decrements magnitudes, so with change rate `beta`:

```
h_stego(d) = h_cover(d) * (1 - beta) + h_cover(d + 1) * beta
```

Least squares over `d` in {1, 2} gives `beta`. On clean covers it should read
zero. It reads **-0.152, with a standard deviation of 0.010.**

The bias is real and has a cause: the carrier is already JPEG-compressed, so
the cropped recompression is *doubly* compressed and its histogram is
systematically more concentrated toward zero than a singly-compressed cover's.

What matters is that the bias is **stable**. A standard deviation of 0.010
against a mean offset of 0.152 makes this a perfectly good relative statistic
and a useless absolute one. So the finding reports a displacement from a
measured clean operating point, never "the change rate is X" -- and the
operating point of -0.13 is two standard deviations above the clean mean,
measured rather than chosen.

## The claim this lab had to withdraw

An earlier version used the zero-excess statistic to name F5 versus nsF5:
shrinkage turns magnitude-one coefficients into zeros, nsF5 does not, so
excess zeros should identify F5.

Measured discrimination between the two, given only stego images:

| payload | AUC via zero excess | AUC via beta |
|---|---|---|
| 0.05 bpp | 0.622 | 0.811 |
| 0.15 bpp | 0.736 | 0.984 |

The zero-excess route barely works, and not for want of tuning. The
calibration reference is computed *from the stego image*, so any embedder that
alters pixels also shifts the reference, and the shrinkage signal does not
survive the subtraction. Shrinkage is real in coefficient space -- gate G2
measures it directly -- but calibration does not isolate it.

So the finding names the **family**, not the member. `algorithm="f5-family"`.

## What beta separates them by instead, and why it matters

Beta does discriminate F5 from nsF5, and the reason follows straight from G2.
Shrinkage wastes changes, so at the same payload F5 modifies about twice as
many coefficients:

| embedder at 0.15 bpp | true change rate |
|---|---|
| F5, k=3 | 0.099 |
| shrinkage-free variant, k=3 | 0.044 |

That inverts the usual argument for nsF5. The textbook version is that it
removes a histogram artefact. The measured version is that it costs less
payload (G2: 45.3% of embedding efficiency) **and** changes half as many
coefficients for the same message -- a security gain the histogram story never
mentions.

## Reproduce

```bash
python3 -m pytest tests/test_labs_d.py -q
python3 gates/g2_classical.py
```

## What it teaches

Calibration is powerful and it is not free: it estimates the reference from
the object under examination, so anything that moves the object moves the
reference. Ask what a calibrated statistic can still see after that
subtraction before deciding what it proves.

---

[Chinese version](README_zh.md)
