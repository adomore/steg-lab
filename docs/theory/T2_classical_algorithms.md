# T2 -- Classical embedding algorithms

> Gate: **G2** -- `python3 gates/g2_classical.py` -- PASSED

## 2.1 Why implement them

You cannot build a detector for an algorithm you have not implemented,
because you will not know which of its properties are essential and which
are incidental. The clearest case is the pair this chapter opens with.

## 2.2 LSB replacement and LSB matching

**Replacement** overwrites the last bit. **Matching** adds or subtracts one
at random when the bit does not already agree. They sound like variants of
one idea. They are not.

Replacement can only ever move a value between the two members of one pair:
2i to 2i+1, or back. So `floor(x/2)` is invariant, and the histogram's pair
counts are driven towards their common mean. That invariance is a
*structure*, and RS analysis, Sample Pair Analysis and Weighted Stego are
all estimators of how far it has been eroded.

Matching crosses pair boundaries. The structure never forms.

The change to the embedder is one line. Gate G4 measures what it costs the
detectors: Weighted Stego reaches AUC 1.000 against replacement at 0.25 bits
per pixel, and 0.550 against matching at the same payload. T4 develops this.

Both cost one change per two embedded bits on average, so the embedding
efficiency of each is 2.0 -- one bit per change is the naive baseline that
matrix encoding exists to beat.

## 2.3 Jsteg and the first real attack

Jsteg does LSB replacement on quantised DCT coefficients, skipping the
values 0 and 1. The skip is defensible on its own terms: changing them would
be conspicuous. But it means the histogram pairs Jsteg touches get flattened
while the pair it skips does not.

Gate G2 criterion D measures the contrast on real coefficients. The
imbalance between the counts at 2 and 3 falls from 0.334 to 0.034, while the
ratio between the counts at 0 and 1 drifts by under 5%.

That contrast is the entire basis of the chi-square attack -- the first
published break of a real steganographic tool, and it arrived within a year.
A design decision made for one good reason created the signature.

## 2.4 F5 and matrix encoding

Matrix encoding is the idea that made F5 matter. Instead of writing one bit
per coefficient, use the (1, 2^k - 1, k) Hamming code: write k bits into
2^k - 1 coefficients by changing **at most one** of them. The syndrome of
the current LSBs says which single position to flip, and when the syndrome
already matches, nothing changes at all.

| quantity | formula |
|---|---|
| embedding efficiency | `e = k / (1 - 2^-k)` |
| embedding rate | `k / (2^k - 1)` bits per coefficient |

Gate G2 measures both against real coefficients:

| k | efficiency theory | measured | error | rate theory | measured |
|---|---|---|---|---|---|
| 1 | 2.0000 | 1.9923 | 0.38% | 1.0000 | 1.0000 |
| 2 | 2.6667 | 2.6542 | 0.47% | 0.6667 | 0.6666 |
| 3 | 3.4286 | 3.4422 | 0.40% | 0.4286 | 0.4285 |
| 4 | 4.2667 | 4.2678 | 0.03% | 0.2667 | 0.2666 |

Read the two columns together. Raising k buys efficiency and costs capacity:
k=4 changes the carrier a quarter as often per bit as k=1, but carries a
quarter of the payload. The choice of k is a direct trade of payload against
detectability, made explicit.

## 2.5 Shrinkage, and what it actually costs

F5 changes a coefficient by *decrementing its magnitude*. When a coefficient
of magnitude 1 is decremented it becomes 0 -- and zeros are not on the
extraction path, so the receiver would desynchronise. F5's answer is to
discard that block and re-send its bits in the next one.

The usual description of the consequence is a histogram artefact: the counts
at plus and minus 1 fall further than embedding alone explains. True, but it
undersells the problem. **A shrinkage event spends a coefficient change and
carries no bits.** The cost is payload.

Gate G2 criterion C quantifies it at k=3 on real coefficients:

| | plain F5 | shrinkage-free variant |
|---|---|---|
| shrinkage events | 11,742 | 0 |
| embedding efficiency | 1.87 | 3.41 |
| embedding rate (bits/coefficient) | 0.2335 | 0.4285 |

**Shrinkage costs 45.3% of the embedding efficiency and 45.5% of the rate.**
Plain F5 at k=3 achieves an efficiency of 1.87 -- *worse than plain LSB's
2.0*, which is the whole thing matrix encoding was supposed to beat.

That is the real argument for nsF5, and it is much stronger than the
histogram notch.

A note on honesty: G2's criteria A and B originally ran against plain F5 and
failed by a consistent ~45%. That was not an implementation defect; the gate
was testing the wrong object, because plain F5 *cannot* meet the textbook
figures. The criteria were moved to the code where the arithmetic applies
and the shortfall became criterion C's subject.

## 2.6 The shrinkage-free variant here is not nsF5

The variant used above increments magnitude-1 coefficients to 2 instead of
decrementing them to 0. This preserves the extraction rule and eliminates
shrinkage by construction, which is enough to measure the penalty.

Real nsF5 uses **wet paper codes**: the embedder marks unusable positions as
"wet" and the code finds a solution that avoids them, which keeps capacity
that this simplification gives up. Wet paper codes are P2 material.

## 2.7 What T4 needs from this chapter

Three facts, all now measured rather than asserted:

1. Replacement leaves a pair-structure invariant; matching does not.
2. Jsteg flattens the pairs it touches and not the pair it skips.
3. F5's efficiency figures are exact when shrinkage is removed, and plain F5
   falls 45% short of them.

## 2.8 Further reading

Westfeld and Pfitzmann (1999) on attacks against Jsteg and the chi-square
test; Westfeld (2001) for F5; Fridrich, Goljan and Soukal (2007) for wet
paper codes and nsF5; Fridrich (2009) chapters 7 and 9.

---

Previous: [T1 -- Carriers and embedding domains](T1_carriers_and_domains.md) |
Next: [T4 -- Statistical steganalysis](T4_statistical_steganalysis.md) |
[Chinese version](T2_classical_algorithms_zh.md)
