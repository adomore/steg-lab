"""Classical embedding algorithms, implemented from scratch.

T2's position is that you cannot build a detector for an algorithm you have
not implemented, because you will not know which of its properties are
essential and which are incidental. The clearest example is in this file:
LSB replacement and LSB matching sound like variants of one idea and are
not. Replacement introduces a *structural* asymmetry between even and odd
values -- it can only ever move 2i to 2i+1 or 2i+1 to 2i, never across a
pair boundary. Matching moves plus or minus one at random, so no such
asymmetry exists.

That single difference is why RS analysis and Sample Pair Analysis reach
AUC above 0.95 on one and collapse to near chance on the other. Gate G4
measures both numbers rather than asserting them.

Everything here operates on numpy arrays. Writing modified DCT coefficients
back into a valid JPEG needs an entropy encoder, which is P2 work for the
C group; T2's claims about F5 are properties of the code, not of the file
format, so they are measured on coefficient arrays directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


# --------------------------------------------------------------------------
# Spatial domain
# --------------------------------------------------------------------------

@dataclass
class EmbedResult:
    stego: np.ndarray
    bits_embedded: int
    changes: int
    positions: Optional[np.ndarray] = None

    @property
    def embedding_efficiency(self) -> float:
        """Bits carried per element actually modified."""
        return self.bits_embedded / self.changes if self.changes else float("inf")

    @property
    def change_rate(self) -> float:
        return self.changes / self.stego.size


def _payload_bits(rng: np.random.Generator, n: int) -> np.ndarray:
    return rng.integers(0, 2, n, dtype=np.uint8)


def _positions(size: int, n: int, seed: Optional[int]) -> np.ndarray:
    if seed is None:
        return np.arange(n)
    return np.random.default_rng(seed).permutation(size)[:n]


def lsb_replacement(cover: np.ndarray, rate: float, seed: int = 0,
                    spread_seed: Optional[int] = 12345) -> EmbedResult:
    """LSB replacement: overwrite the least significant bit.

    `rate` is the relative payload in bits per element. The value that
    matters for detection is always relative, never absolute -- the same
    payload is trivially visible in a small carrier and invisible in a
    large one.
    """
    flat = cover.reshape(-1).astype(np.uint8).copy()
    n = int(round(rate * flat.size))
    if n == 0:
        return EmbedResult(cover.copy(), 0, 0)

    rng = np.random.default_rng(seed)
    bits = _payload_bits(rng, n)
    idx = _positions(flat.size, n, spread_seed)

    before = flat[idx].copy()
    flat[idx] = (flat[idx] & 0xFE) | bits
    changes = int(np.count_nonzero(before != flat[idx]))

    return EmbedResult(flat.reshape(cover.shape), n, changes, idx)


def lsb_matching(cover: np.ndarray, rate: float, seed: int = 0,
                 spread_seed: Optional[int] = 12345) -> EmbedResult:
    """LSB matching (+/-1 embedding): adjust by one in a random direction.

    When the LSB already matches, nothing happens. When it does not, the
    value moves up or down by one, chosen at random, which is what destroys
    the even/odd pair structure that replacement leaves behind.

    Boundary values are forced inward -- 0 can only go up, 255 only down --
    which is itself a (small) statistical trace, and the reason detectors
    that examine saturated regions exist.
    """
    flat = cover.reshape(-1).astype(np.int16).copy()
    n = int(round(rate * flat.size))
    if n == 0:
        return EmbedResult(cover.copy(), 0, 0)

    rng = np.random.default_rng(seed)
    bits = _payload_bits(rng, n)
    idx = _positions(flat.size, n, spread_seed)

    current = flat[idx]
    mismatch = (current & 1).astype(np.uint8) != bits
    step = rng.choice(np.array([-1, 1], dtype=np.int16), size=n)
    step[current == 0] = 1
    step[current == 255] = -1

    updated = current.copy()
    updated[mismatch] = current[mismatch] + step[mismatch]

    flat[idx] = updated
    changes = int(np.count_nonzero(mismatch))

    return EmbedResult(flat.reshape(cover.shape).astype(np.uint8), n, changes, idx)


def extract_lsb(stego: np.ndarray, nbits: int,
                spread_seed: Optional[int] = 12345) -> np.ndarray:
    flat = stego.reshape(-1)
    idx = _positions(flat.size, nbits, spread_seed)
    return (flat[idx] & 1).astype(np.uint8)


# --------------------------------------------------------------------------
# JPEG DCT domain
# --------------------------------------------------------------------------

def jsteg(coeffs: np.ndarray, rate: float, seed: int = 0) -> EmbedResult:
    """Jsteg: LSB replacement on DCT coefficients, skipping 0 and 1.

    The skip rule is what gives Jsteg its fingerprint. Coefficients of
    magnitude 0 and 1 are excluded because changing them would be
    conspicuous -- and because decrementing a +/-1 to 0 would remove it from
    the extraction path entirely, desynchronising the receiver. The
    exclusion means the histogram bins at +/-2 and +/-3 (and every higher
    pair) get equalised while 0 and 1 do not. That asymmetry is exactly what
    the chi-square attack keys on -- the first published attack on a real
    steganographic tool, and it took less than a year.

    `coeffs` is a (blocks, 64) integer array as produced by
    steganalysis.jpeg.decode_scan(collect_coefficients=True).
    """
    flat = coeffs.reshape(-1).astype(np.int32).copy()
    # Magnitude, not value: -1 must be skipped too, or embedding a 0 bit
    # turns it into 0 and drops it out of the extraction path.
    usable = np.flatnonzero(np.abs(flat) > 1)
    n = min(int(round(rate * usable.size)), usable.size)
    if n == 0:
        return EmbedResult(coeffs.copy(), 0, 0)

    rng = np.random.default_rng(seed)
    bits = _payload_bits(rng, n)
    idx = usable[:n]

    before = flat[idx].copy()
    magnitude = np.abs(flat[idx])
    sign = np.sign(flat[idx])
    new_mag = (magnitude & ~1) | bits
    flat[idx] = sign * new_mag

    changes = int(np.count_nonzero(before != flat[idx]))
    return EmbedResult(flat.reshape(coeffs.shape), n, changes, idx)


@dataclass
class F5Result(EmbedResult):
    shrinkage_events: int = 0
    blocks_used: int = 0
    k: int = 1

    @property
    def theoretical_efficiency(self) -> float:
        """e = k / (1 - 2^-k) for the (1, 2^k - 1, k) Hamming code."""
        return self.k / (1.0 - 2.0 ** (-self.k))

    @property
    def theoretical_rate(self) -> float:
        """Bits per coefficient: k / (2^k - 1)."""
        return self.k / (2 ** self.k - 1)


def _hamming_syndrome(window: np.ndarray, k: int) -> int:
    """XOR of the 1-based indices of every window position whose bit is 1."""
    positions = np.flatnonzero(window) + 1
    syndrome = 0
    for p in positions:
        syndrome ^= int(p)
    return syndrome


def f5(coeffs: np.ndarray, rate: float, k: int = 3, seed: int = 0,
       no_shrinkage: bool = False) -> F5Result:
    """F5 with (1, 2^k - 1, k) matrix encoding.

    Matrix encoding is the reason F5 mattered. Instead of writing one bit per
    coefficient, it writes k bits into 2^k - 1 coefficients by changing at
    most one of them. The syndrome of the current LSBs tells you which single
    position to flip; if the syndrome already matches, you change nothing.

    Embedding efficiency:

        e = k / (1 - 2^-k)

    k=1 gives 2.0 (plain LSB), k=3 gives 3.43, k=4 gives 4.27. The capacity
    falls as k rises -- k / (2^k - 1) bits per coefficient -- so the choice
    is a direct trade of payload against detectability.

    **Shrinkage.** F5 changes a coefficient by decrementing its magnitude.
    When a coefficient of magnitude 1 is decremented it becomes 0, and zeros
    are not part of the extraction path, so the receiver would desynchronise.
    F5's answer is to re-embed that block's bits in the next block. The cost
    is visible in the histogram: the count at +/-1 falls and the count at 0
    rises by more than embedding alone would explain. That notch is the
    signature nsF5 was designed to remove.

    `no_shrinkage=True` selects the simplified variant described in T2 5.4:
    coefficients of magnitude 1 are *incremented* to magnitude 2 rather than
    decremented to 0. This preserves the extraction rule and eliminates
    shrinkage entirely. Real nsF5 uses wet paper codes instead, which keeps
    the capacity this simplification gives up; the difference is measured in
    gate G2 rather than glossed over.
    """
    n_window = 2 ** k - 1
    flat = coeffs.reshape(-1).astype(np.int32).copy()

    nonzero = np.flatnonzero(flat != 0)
    rng = np.random.default_rng(seed)
    order = rng.permutation(nonzero)

    target_bits = int(round(rate * nonzero.size))
    if target_bits == 0:
        return F5Result(coeffs.copy(), 0, 0, k=k)

    message = _payload_bits(rng, target_bits)

    bits_done = 0
    changes = 0
    shrinkage = 0
    blocks = 0
    cursor = 0

    while bits_done + k <= target_bits and cursor + n_window <= order.size:
        window_idx = order[cursor:cursor + n_window]
        cursor += n_window
        blocks += 1

        lsbs = (np.abs(flat[window_idx]) & 1).astype(np.uint8)
        syndrome = _hamming_syndrome(lsbs, k)

        target = 0
        for bit_i in range(k):
            if message[bits_done + bit_i]:
                target ^= (1 << bit_i)

        change_at = syndrome ^ target
        if change_at != 0:
            pos = window_idx[change_at - 1]
            value = flat[pos]
            magnitude = abs(value)
            sign = 1 if value > 0 else -1

            if magnitude == 1:
                if no_shrinkage:
                    flat[pos] = sign * 2
                else:
                    flat[pos] = 0
                    shrinkage += 1
                    # The block is re-sent: rewind the message pointer and
                    # let the next window carry the same k bits.
                    changes += 1
                    continue
            else:
                flat[pos] = sign * (magnitude - 1)
            changes += 1

        bits_done += k

    result = F5Result(flat.reshape(coeffs.shape), bits_done, changes, k=k)
    result.shrinkage_events = shrinkage
    result.blocks_used = blocks
    return result


def coefficient_histogram(coeffs: np.ndarray, lo: int = -8, hi: int = 8) -> np.ndarray:
    """Histogram of DCT coefficient values over [lo, hi]."""
    flat = coeffs.reshape(-1)
    values = np.arange(lo, hi + 1)
    return np.array([np.count_nonzero(flat == v) for v in values], dtype=np.int64)
