"""A steganalysis CNN written from scratch, because the architecture is the point.

T5 ended with hand-designed residuals -- one difference operator, 686
features, an ensemble on top. T6 replaces the designed residual with a learned
one. What survives that replacement is worth knowing, and the way to find out
is to build the thing and take pieces off it.

Three architectural decisions carry the whole chapter, and each is an ablation
in gate G6 rather than an assertion here:

  * **The first layer is a FIXED high-pass filter, not learned.** This is
    Xu-Net's central contribution. A network trained on raw pixels spends its
    capacity learning to suppress image content, which dominates the stego
    signal by orders of magnitude, and with a few hundred training images it
    never finishes. Handing it the KV kernel starts it where the residual
    already is.
  * **The activation after the first convolution is |x|, not ReLU.** Embedding
    is symmetric: +1 and -1 are equally likely, so the sign of a residual
    carries no information about whether a payload exists. Taking the absolute
    value halves what the network has to learn and throws nothing away.
  * **Pooling is average, never max.** The stego signal is low-amplitude and
    spread across the whole carrier. Max pooling keeps the loudest response in
    each window, which is exactly the wrong summary -- it keeps image content
    and discards the payload.

Everything is numpy. No autograd framework, no GPU, no 800 MB download; the
backward passes are written out, which also means they are inspectable, and
gate G6 checks them against numerical gradients rather than trusting them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

#: The KV high-pass kernel, as used by SRM's residuals and by Xu-Net's fixed
#: first layer. It is a 5x5 approximation of a second-derivative operator: it
#: annihilates smooth content and passes the noise-like component where a
#: payload lives.
KV_KERNEL = np.array([
    [-1, 2, -2, 2, -1],
    [2, -6, 8, -6, 2],
    [-2, 8, -12, 8, -2],
    [2, -6, 8, -6, 2],
    [-1, 2, -2, 2, -1],
], dtype=np.float64) / 12.0


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

def im2col(x: np.ndarray, kh: int, kw: int) -> np.ndarray:
    """(N, C, H, W) -> (N, C*kh*kw, oh*ow). Stride 1, valid padding."""
    windows = sliding_window_view(x, (kh, kw), axis=(2, 3))
    n, c, oh, ow = windows.shape[0], windows.shape[1], windows.shape[2], windows.shape[3]
    cols = windows.transpose(0, 1, 4, 5, 2, 3).reshape(n, c * kh * kw, oh * ow)
    return np.ascontiguousarray(cols)


def col2im(dcols: np.ndarray, shape: Tuple[int, int, int, int],
           kh: int, kw: int) -> np.ndarray:
    """Scatter column gradients back onto the input.

    Written as a loop over the kh*kw kernel offsets rather than with a fancy
    scatter: at most 25 iterations, each one a fully vectorised slice add, and
    the correspondence to the forward pass stays readable.
    """
    n, c, h, w = shape
    oh, ow = h - kh + 1, w - kw + 1
    dx = np.zeros(shape, dtype=np.float64)
    d = dcols.reshape(n, c, kh, kw, oh, ow)
    for i in range(kh):
        for j in range(kw):
            dx[:, :, i:i + oh, j:j + ow] += d[:, :, i, j]
    return dx


@dataclass
class Conv:
    """Valid-padding, stride-1 convolution."""

    in_ch: int
    out_ch: int
    k: int
    #: A convolution followed by batch normalisation does not need a bias.
    #: BN subtracts the batch mean per channel, so adding a constant to the
    #: convolution's output changes nothing -- the true gradient with respect
    #: to that bias is exactly zero. Keeping it wastes parameters and, worse,
    #: puts a degenerate quantity in front of any gradient check: both the
    #: numerical and analytic gradients land at floating-point noise, and a
    #: relative-error metric on two near-zero numbers returns garbage. Gate G6
    #: reported a relative error of exactly 1.00 on conv1.b for that reason.
    use_bias: bool = True
    W: np.ndarray = field(init=False)
    b: np.ndarray = field(init=False)
    trainable: bool = True

    def __post_init__(self) -> None:
        scale = np.sqrt(2.0 / (self.in_ch * self.k * self.k))
        rng = np.random.default_rng(0)
        self.W = rng.normal(0, scale, (self.out_ch, self.in_ch, self.k, self.k))
        self.b = np.zeros(self.out_ch)
        self._cache: Dict = {}

    def seed(self, seed: int) -> None:
        scale = np.sqrt(2.0 / (self.in_ch * self.k * self.k))
        rng = np.random.default_rng(seed)
        self.W = rng.normal(0, scale, (self.out_ch, self.in_ch, self.k, self.k))
        self.b = np.zeros(self.out_ch)

    def forward(self, x: np.ndarray) -> np.ndarray:
        n, c, h, w = x.shape
        cols = im2col(x, self.k, self.k)
        wmat = self.W.reshape(self.out_ch, -1)
        out = np.einsum("fk,nkp->nfp", wmat, cols)
        if self.use_bias:
            out = out + self.b[None, :, None]
        oh, ow = h - self.k + 1, w - self.k + 1
        self._cache = {"cols": cols, "shape": x.shape}
        return out.reshape(n, self.out_ch, oh, ow)

    def backward(self, dout: np.ndarray) -> np.ndarray:
        cols = self._cache["cols"]
        shape = self._cache["shape"]
        n, f, oh, ow = dout.shape
        d = dout.reshape(n, f, oh * ow)
        wmat = self.W.reshape(f, -1)
        self.dW = np.einsum("nfp,nkp->fk", d, cols).reshape(self.W.shape)
        self.db = d.sum(axis=(0, 2)) if self.use_bias else np.zeros_like(self.b)
        dcols = np.einsum("fk,nfp->nkp", wmat, d)
        return col2im(dcols, shape, self.k, self.k)


def avg_pool(x: np.ndarray, size: int = 2) -> np.ndarray:
    n, c, h, w = x.shape
    h2, w2 = h - h % size, w - w % size
    return x[:, :, :h2, :w2].reshape(n, c, h2 // size, size,
                                     w2 // size, size).mean(axis=(3, 5))


def avg_pool_backward(dout: np.ndarray, shape: Tuple[int, ...],
                      size: int = 2) -> np.ndarray:
    n, c, h, w = shape
    h2, w2 = h - h % size, w - w % size
    dx = np.zeros(shape, dtype=np.float64)
    spread = np.repeat(np.repeat(dout, size, axis=2), size, axis=3) / (size * size)
    dx[:, :, :h2, :w2] = spread[:, :, :h2, :w2]
    return dx


def softmax_cross_entropy(logits: np.ndarray, labels: np.ndarray
                          ) -> Tuple[float, np.ndarray]:
    z = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(z)
    probs = exp / exp.sum(axis=1, keepdims=True)
    n = labels.size
    loss = float(-np.log(np.clip(probs[np.arange(n), labels], 1e-12, None)).mean())
    dlogits = probs.copy()
    dlogits[np.arange(n), labels] -= 1.0
    return loss, dlogits / n


# --------------------------------------------------------------------------
# The network
# --------------------------------------------------------------------------

@dataclass
class BatchNorm:
    """Per-channel batch normalisation.

    Not an optional refinement. Without it this network cannot learn at all:
    the KV response on scaled input is small, He initialisation shrinks it
    again at each convolution, and by the global average pool the activations
    and therefore the gradients are numerically negligible. Measured before
    adding it, the network could not overfit 32 samples at any learning rate --
    training loss sat at ln(2) = 0.6931 for 60 epochs. That is why every
    published architecture in this family has normalisation between layers,
    and it is worth knowing as a fact about the optimisation rather than as a
    line in a diagram.
    """

    channels: int
    momentum: float = 0.9
    eps: float = 1e-5

    def __post_init__(self) -> None:
        self.gamma = np.ones((1, self.channels, 1, 1))
        self.beta = np.zeros((1, self.channels, 1, 1))
        self.running_mean = np.zeros((1, self.channels, 1, 1))
        self.running_var = np.ones((1, self.channels, 1, 1))
        self._cache: Dict = {}

    def forward(self, x: np.ndarray, training: bool = True) -> np.ndarray:
        if training:
            mu = x.mean(axis=(0, 2, 3), keepdims=True)
            var = x.var(axis=(0, 2, 3), keepdims=True)
            self.running_mean = (self.momentum * self.running_mean
                                 + (1 - self.momentum) * mu)
            self.running_var = (self.momentum * self.running_var
                                + (1 - self.momentum) * var)
        else:
            mu, var = self.running_mean, self.running_var
        inv = 1.0 / np.sqrt(var + self.eps)
        xhat = (x - mu) * inv
        self._cache = {"xhat": xhat, "inv": inv}
        return self.gamma * xhat + self.beta

    def backward(self, dout: np.ndarray) -> np.ndarray:
        xhat, inv = self._cache["xhat"], self._cache["inv"]
        self.dgamma = (dout * xhat).sum(axis=(0, 2, 3), keepdims=True)
        self.dbeta = dout.sum(axis=(0, 2, 3), keepdims=True)
        dxhat = dout * self.gamma
        m = dout.shape[0] * dout.shape[2] * dout.shape[3]
        return inv * (dxhat
                      - dxhat.sum(axis=(0, 2, 3), keepdims=True) / m
                      - xhat * (dxhat * xhat).sum(axis=(0, 2, 3), keepdims=True) / m)


@dataclass
class StegoNet:
    """A small Xu-Net-shaped detector for 64x64 grayscale carriers.

    input 1x64x64
      fixed KV high-pass 5x5           -> 1x60x60   (not trained)
      conv 8 @5x5, BN, ABS, avgpool2   -> 8x28x28
      conv 16 @5x5, BN, ReLU, avgpool2 -> 16x12x12
      conv 32 @3x3, BN, ReLU           -> 32x10x10
      global average pool           -> 32
      fully connected               -> 2

    About 8,100 trainable parameters. Small on purpose: the question this
    chapter asks is which architectural choices matter, and that question is
    answered by ablation on something trainable in minutes, not by scale.
    """

    high_pass: bool = True
    abs_activation: bool = True
    #: Xu-Net's ordering is convolution -> ABS -> normalisation. Placing the
    #: normalisation FIRST, as an earlier version of this file did, breaks the
    #: activation: batch normalisation centres its output at zero, so |x| of it
    #: is a half-normal with mean about +0.8 and nothing re-centres it before
    #: the next convolution. Measured, that ordering made ABS lose to ReLU by
    #: 0.097 at 128px -- which reads as evidence against the published claim
    #: and is really evidence about where the layer was put.
    abs_before_norm: bool = True
    seed: int = 1

    def __post_init__(self) -> None:
        # No convolution bias: each is followed by batch normalisation.
        self.c1 = Conv(1, 8, 5, use_bias=False)
        self.c2 = Conv(8, 16, 5, use_bias=False)
        self.c3 = Conv(16, 32, 3, use_bias=False)
        self.n1, self.n2, self.n3 = BatchNorm(8), BatchNorm(16), BatchNorm(32)
        for i, layer in enumerate((self.c1, self.c2, self.c3)):
            layer.seed(self.seed * 100 + i)
        rng = np.random.default_rng(self.seed + 7)
        self.Wf = rng.normal(0, np.sqrt(2.0 / 32), (32, 2))
        self.bf = np.zeros(2)
        self._m: Dict[int, np.ndarray] = {}

    # ---------------------------------------------------------------- shapes
    @property
    def n_parameters(self) -> int:
        return int(sum(p.size for p in
                       (self.c1.W, self.c2.W, self.c3.W, self.Wf, self.bf,
                        self.n1.gamma, self.n1.beta, self.n2.gamma,
                        self.n2.beta, self.n3.gamma, self.n3.beta)))

    # --------------------------------------------------------------- forward
    def forward(self, x: np.ndarray, training: bool = True) -> np.ndarray:
        cache = {}
        h = x.astype(np.float64)

        if self.high_pass:
            kv = KV_KERNEL[None, None, :, :]
            cols = im2col(h, 5, 5)
            n, _, hh, ww = h.shape
            h = np.einsum("fk,nkp->nfp", kv.reshape(1, -1), cols).reshape(
                n, 1, hh - 4, ww - 4)
        cache["after_hp"] = h.shape

        z1 = self.c1.forward(h)
        if self.abs_before_norm:
            if self.abs_activation:
                shaped, cache["sign1"] = np.abs(z1), np.sign(z1)
            else:
                shaped = np.maximum(z1, 0.0)
                cache["sign1"] = (z1 > 0).astype(np.float64)
            act1 = self.n1.forward(shaped, training)
        else:
            a1 = self.n1.forward(z1, training)
            if self.abs_activation:
                act1, cache["sign1"] = np.abs(a1), np.sign(a1)
            else:
                act1 = np.maximum(a1, 0.0)
                cache["sign1"] = (a1 > 0).astype(np.float64)
        cache["shape1"] = act1.shape
        p1 = avg_pool(act1, 2)

        a2 = self.n2.forward(self.c2.forward(p1), training)
        act2 = np.maximum(a2, 0.0)
        cache["mask2"] = (a2 > 0).astype(np.float64)
        cache["shape2"] = act2.shape
        p2 = avg_pool(act2, 2)

        a3 = self.n3.forward(self.c3.forward(p2), training)
        act3 = np.maximum(a3, 0.0)
        cache["mask3"] = (a3 > 0).astype(np.float64)
        cache["shape3"] = act3.shape

        gap = act3.mean(axis=(2, 3))
        cache["gap_hw"] = act3.shape[2] * act3.shape[3]
        cache["gap"] = gap

        logits = gap @ self.Wf + self.bf
        self._cache = cache
        return logits

    # -------------------------------------------------------------- backward
    def backward(self, dlogits: np.ndarray) -> None:
        c = self._cache
        self.dWf = c["gap"].T @ dlogits
        self.dbf = dlogits.sum(axis=0)
        dgap = dlogits @ self.Wf.T

        n, ch = dgap.shape
        h3, w3 = c["shape3"][2], c["shape3"][3]
        dact3 = np.repeat(np.repeat(dgap[:, :, None, None], h3, axis=2),
                          w3, axis=3) / c["gap_hw"]
        da3 = self.n3.backward(dact3 * c["mask3"])
        dp2 = self.c3.backward(da3)

        dact2 = avg_pool_backward(dp2, c["shape2"], 2)
        da2 = self.n2.backward(dact2 * c["mask2"])
        dp1 = self.c2.backward(da2)

        dact1 = avg_pool_backward(dp1, c["shape1"], 2)
        if self.abs_before_norm:
            da1 = self.n1.backward(dact1) * c["sign1"]
        else:
            da1 = self.n1.backward(dact1 * c["sign1"])
        self.c1.backward(da1)

    # ------------------------------------------------------------------ step
    def parameters(self) -> List[Tuple[np.ndarray, np.ndarray]]:
        return [(self.c1.W, self.c1.dW),
                (self.c2.W, self.c2.dW),
                (self.c3.W, self.c3.dW),
                (self.Wf, self.dWf), (self.bf, self.dbf),
                (self.n1.gamma, self.n1.dgamma), (self.n1.beta, self.n1.dbeta),
                (self.n2.gamma, self.n2.dgamma), (self.n2.beta, self.n2.dbeta),
                (self.n3.gamma, self.n3.dgamma), (self.n3.beta, self.n3.dbeta)]

    def step(self, lr: float, momentum: float = 0.9) -> None:
        for i, (p, g) in enumerate(self.parameters()):
            v = self._m.get(i)
            if v is None:
                v = np.zeros_like(p)
            v = momentum * v - lr * g
            self._m[i] = v
            p += v

    # ------------------------------------------------------------- inference
    def scores(self, x: np.ndarray, batch: int = 64) -> np.ndarray:
        """P(stego) for each carrier."""
        out = []
        for i in range(0, len(x), batch):
            logits = self.forward(x[i:i + batch], training=False)
            z = logits - logits.max(axis=1, keepdims=True)
            e = np.exp(z)
            out.append((e / e.sum(axis=1, keepdims=True))[:, 1])
        return np.concatenate(out)


@dataclass
class TrainLog:
    epochs: int
    seconds: float
    parameters: int
    final_loss: float
    loss_curve: List[float]


#: Global affine input scaling. A GLOBAL constant is fine; PER-IMAGE variance
#: normalisation is not. The latter is standard for object recognition and
#: wrong here, because it rescales residual amplitude -- the quantity being
#: measured -- differently for each carrier. A shared constant leaves every
#: carrier's amplitude in the same units.
#:
#: The divisor is not cosmetic. Without it the KV response on pixel-scale input
#: drives the logits far enough that the softmax saturates, the cross-entropy
#: hits its clipping floor, and the loss surface goes locally flat -- which
#: showed up first as a gradient check reporting a relative error of exactly
#: 1.0 on every parameter, because the numerical gradient was zero while the
#: analytic one was not.
INPUT_SCALE = 128.0


def normalise(images: np.ndarray) -> np.ndarray:
    """Centre and scale by a shared constant."""
    return (images.astype(np.float64)[:, None, :, :] - 128.0) / INPUT_SCALE


def train(net: StegoNet, x: np.ndarray, y: np.ndarray, epochs: int = 30,
          batch: int = 32, lr: float = 0.002, seed: int = 0,
          verbose: bool = False) -> TrainLog:
    rng = np.random.default_rng(seed)
    curve: List[float] = []
    t0 = time.perf_counter()
    for epoch in range(epochs):
        order = rng.permutation(len(x))
        total = 0.0
        steps = 0
        for i in range(0, len(order) - batch + 1, batch):
            idx = order[i:i + batch]
            logits = net.forward(x[idx])
            loss, dlogits = softmax_cross_entropy(logits, y[idx])
            net.backward(dlogits)
            net.step(lr)
            total += loss
            steps += 1
        curve.append(total / max(steps, 1))
        if verbose:
            print(f"  epoch {epoch + 1:>3}  loss {curve[-1]:.4f}")
    return TrainLog(epochs=epochs, seconds=time.perf_counter() - t0,
                    parameters=net.n_parameters,
                    final_loss=curve[-1] if curve else float("nan"),
                    loss_curve=curve)
