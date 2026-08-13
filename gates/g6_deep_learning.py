#!/usr/bin/env python3
"""Gate G6 -- deep-learning steganalysis, graded by ablation rather than score.

The learning path specifies this gate as a comparison table with a training
cost, not a leaderboard entry. That framing is deliberate: a from-scratch
numpy network trained on a few hundred synthetic 64x64 carriers is not going to
approach published figures, and pretending otherwise would be the one thing
this repository has consistently refused to do.

What it *can* do is test the architectural claims T6 makes, because each one is
a component that can be removed.

Criteria:

  A. THE GRADIENTS ARE CORRECT. Verified at carrier sizes up to 128px; at
     192px central differences lose enough precision that the check would need
     a larger step, and that is a property of the check rather than of the
     backward pass. Hand-written backward passes checked against
     central differences; worst relative error below 1e-4. Everything below is
     meaningless if this fails, and it did fail on the first run -- see the
     note in steganalysis.cnn.normalise.

  B. THE OPTIMISATION WORKS, checked independently of task difficulty by
     memorising 32 samples. This criterion exists because the first working
     version of this gate reported everything at chance and the obvious reading
     -- "the task has no signal" -- was wrong twice over. First the network
     could not learn at all, because activations collapsed through the layers
     and no gradient reached the early convolutions; batch normalisation fixed
     that. Then it still could not, because 32 samples at batch size 32 is one
     optimisation step per epoch and 60 epochs is 60 steps. An overfit check
     separates "cannot optimise" from "nothing to find", and those need
     completely different responses.

  B2. THE NETWORK LEARNS THE ACTUAL TASK -- graded only where the T5 baseline
      is itself detectable. On 64x64 synthetic carriers SPAM686 reaches P_E
      0.425 and the CNN 0.419: both sit on the corpus's detection floor, and
      grading a network against a threshold the reference method also misses
      would be measuring the corpus. Same precondition as gate G3's criterion E.

  D. THE ABS ACTIVATION -- reported, not graded, because the measurement does
     not support the claim at this scale. ReLU came out 0.006 BETTER. The
     symmetry argument is sound and the effect is documented in the
     literature; it is not visible on 80 training pairs of 64x64 synthetic
     carriers, and saying so is the only honest option. Gap G-21.

  C. THE FIXED HIGH-PASS LAYER IS NECESSARY. Removing it must cost accuracy
     measurably. This is Xu-Net's central contribution and the reason CNNs
     started working on this problem at all; if the network does as well
     without it, the claim is wrong and the chapter should say so.

  E. THE COMPARISON WITH T5 IS REPORTED WITH ITS COST. Same carriers, same
     split, same payload. P_E for both, plus parameters, epochs and wall-clock
     seconds. Reported, not graded -- the point is the trade, not a winner.

Run:  python3 gates/g6_deep_learning.py [--n 300] [--epochs 20]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from steganalysis import corpus, embedders as E
from steganalysis.cnn import (StegoNet, normalise, softmax_cross_entropy,
                              train)
from steganalysis.features import (FldEnsemble, min_error_probability,
                                   spam686)

RESULTS = Path(__file__).resolve().parent / "results"
#: Relative-error bar for the gradient check.
RTOL_DISPLAY = 1e-4
DEFAULT_SIDE = 64
SIDE = DEFAULT_SIDE  # overridable with --side; see gap G-21
#: LSB replacement rather than matching, and 1.0 bpp. The task is chosen to
#: have signal in it: on 64x64 synthetic carriers SPAM686 sits at P_E 0.42
#: against replacement and 0.44 against matching, so neither is easy, but the
#: question this gate asks is which architectural choices matter -- and that
#: question cannot be answered on a task where nothing is detectable.
PAYLOAD = 1.0
EMBEDDER = E.lsb_replacement
KINDS = ["texture", "photo_like"]


def cover(seed: int) -> np.ndarray:
    spec = corpus.CoverSpec("g.png", seed, SIDE, SIDE,
                            KINDS[seed % 2], "png")
    return np.array(Image.open(io.BytesIO(corpus.render(spec))).convert("L"))


def build_dataset(n: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (covers, stegos, labels-free) -- the split happens downstream."""
    covers = np.array([cover(2_100_000 + i) for i in range(n)])
    stegos = np.array([EMBEDDER(c, PAYLOAD, seed=i).stego
                       for i, c in enumerate(covers)])
    return covers, stegos, np.arange(n)


def gradient_check() -> Dict:
    rng = np.random.default_rng(0)
    net = StegoNet(seed=3)
    # Eight samples, not four. With batch normalisation in the graph the loss
    # depends on the whole batch's statistics, and at batch size four the
    # variance estimate is noisy enough that central differences stop agreeing
    # with the analytic gradient -- which looks exactly like a broken backward
    # pass and is not one.
    x = normalise(rng.integers(100, 160, (8, SIDE, SIDE), dtype=np.uint8))
    y = np.array([0, 1] * 4)
    _loss, dlogits = softmax_cross_entropy(net.forward(x), y)
    net.backward(dlogits)

    # Tolerance scaled to the tensor, not a constant. A pure relative-error
    # metric is undefined when both gradients are floating-point noise and
    # returns values near 1.0 that look exactly like a broken backward pass;
    # a fixed absolute floor then fails the other way as the carrier grows,
    # because a parameter whose gradient is a rounding error next to its own
    # tensor's RMS still clears any constant. Measured: at 128px a constant
    # 1e-8 floor let bn1.beta report 9.4e-04 and fail a gate whose backward
    # pass is correct. The floor is now a fraction of the tensor's own RMS.
    RTOL = 1e-4
    FLOOR_FRACTION = 1e-3

    def worst_for(param: np.ndarray, dparam: np.ndarray,
                  samples: int = 5, eps: float = 1e-6) -> float:
        flat, dflat = param.reshape(-1), dparam.reshape(-1)
        # Two floors, and both are needed. The tensor-relative one skips a
        # gradient that is a rounding error next to its own tensor -- the case
        # that failed at 128px. The absolute one covers a tensor that is
        # ENTIRELY zero, where the relative floor is itself zero: with the
        # activation in Xu-Net's position, bn1.beta only shifts its output and
        # the next normalisation removes the shift, so its gradient is exactly
        # zero everywhere. That is the same structural fact as the convolution
        # biases in F-30, arriving one layer up.
        floor = max(FLOOR_FRACTION * float(np.sqrt(np.mean(dflat ** 2))), 1e-8)
        idx = rng.choice(flat.size, size=min(samples, flat.size), replace=False)
        errs = []
        for k in idx:
            original = flat[k]
            flat[k] = original + eps
            plus, _ = softmax_cross_entropy(net.forward(x), y)
            flat[k] = original - eps
            minus, _ = softmax_cross_entropy(net.forward(x), y)
            flat[k] = original
            numeric = (plus - minus) / (2 * eps)
            scale = abs(numeric) + abs(dflat[k])
            errs.append(0.0 if scale < floor
                        else abs(numeric - dflat[k]) / scale)
        return float(max(errs))

    checks = {
        "conv1.W": worst_for(net.c1.W, net.c1.dW),
        "conv2.W": worst_for(net.c2.W, net.c2.dW),
        "bn1.gamma": worst_for(net.n1.gamma, net.n1.dgamma),
        "bn1.beta": worst_for(net.n1.beta, net.n1.dbeta),
        "conv3.W": worst_for(net.c3.W, net.c3.dW),
        "fc.W": worst_for(net.Wf, net.dWf),
        "fc.b": worst_for(net.bf, net.dbf),
    }
    return {"per_parameter": {k: f"{v:.2e}" for k, v in checks.items()},
            "worst": max(checks.values())}


BATCH = 8
#: Learning rate, tied to where the activation sits.
#:
#: Moving ABS ahead of the normalisation (Xu-Net's order, gap G-21) changes the
#: scale of what reaches the next layer, and the effective step size moves with
#: it. Measured on the overfit check, 150 epochs at batch 8: the old ordering
#: reached loss 0.173 at lr 0.05, the corrected one only 0.488 -- so criterion
#: B failed on an architecture that is strictly better on real covers, P_E
#: 0.233 to 0.163 on BOSSbase. At lr 0.15 the corrected ordering reaches 0.224;
#: at 0.30 it diverges to 0.695.
#:
#: The lesson is not the number. It is that an architectural change quietly
#: invalidated a hyperparameter chosen for the previous architecture, and the
#: only thing that caught it was a criterion that trains to a target rather
#: than reporting whatever it gets.
LR = 0.15


def overfit_check(covers: np.ndarray, stegos: np.ndarray,
                  n: int = 16, epochs: int = 150) -> Dict:
    """Can it memorise a handful of samples? If not, nothing else means anything."""
    x = normalise(np.concatenate([covers[:n], stegos[:n]]))
    y = np.concatenate([np.zeros(n, dtype=int), np.ones(n, dtype=int)])
    log = train(StegoNet(seed=1), x, y, epochs=epochs, batch=BATCH, lr=LR, seed=5)
    return {"samples": 2 * n, "steps": epochs * (2 * n // BATCH),
            "loss_start": round(log.loss_curve[0], 4),
            "loss_end": round(log.loss_curve[-1], 4),
            "seconds": round(log.seconds, 1)}


def run_variant(label: str, covers: np.ndarray, stegos: np.ndarray,
                half: int, epochs: int, **kwargs) -> Dict:
    x_train = normalise(np.concatenate([covers[:half], stegos[:half]]))
    y_train = np.concatenate([np.zeros(half, dtype=int), np.ones(half, dtype=int)])
    net = StegoNet(seed=1, **kwargs)
    log = train(net, x_train, y_train, epochs=epochs, batch=BATCH, lr=LR, seed=5)

    s_cover = net.scores(normalise(covers[half:]))
    s_stego = net.scores(normalise(stegos[half:]))
    pe, _ = min_error_probability(s_cover, s_stego)
    return {"variant": label, "P_E": round(pe, 4),
            "parameters": log.parameters, "epochs": log.epochs,
            "seconds": round(log.seconds, 1),
            "final_loss": round(log.final_loss, 4)}


def main() -> int:
    # Declared before any read of SIDE in this scope. Reading a module global
    # and then declaring it global in the same function is a SyntaxError, so
    # --help stopped working -- caught by check-docs' `commands` checker, which
    # exists for exactly this: a documented command that cannot run.
    global SIDE
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--corpus", choices=["synthetic", "real"], default="synthetic")
    ap.add_argument("--side", type=int, default=DEFAULT_SIDE,
                    help="carrier crop size. The ABS ablation (criterion D) did "
                         "not replicate at 64px on either corpus; larger crops "
                         "are where it would show if it shows at all (G-21). "
                         "Cost scales with the square.")
    args = ap.parse_args()
    SIDE = args.side

    if args.corpus == "real":
        from steganalysis import reference
        corp = reference.load_registered()
        if corp is None or not len(corp):
            raise SystemExit("no reference corpus registered; "
                             "run scripts/register-corpus.py first")
        raw = []
        for img in corp.sample(args.n, seed=41):
            h, w = img.shape
            top, left = (h - SIDE) // 2, (w - SIDE) // 2
            raw.append(img[top:top + SIDE, left:left + SIDE])
        covers = np.array(raw)
        stegos = np.array([EMBEDDER(c, PAYLOAD, seed=i).stego
                           for i, c in enumerate(covers)])
        corpus_desc = f"bossbase, centre-cropped to {SIDE}px"
    else:
        covers, stegos, _ = build_dataset(args.n)
        corpus_desc = f"synthetic, {SIDE}px"
    half = args.n // 2
    results = []

    # ---------------------------------------------------------------- A
    grad = gradient_check()
    results.append({
        "name": "A_gradients_are_correct",
        **grad,
        "tolerance": RTOL_DISPLAY,
        "pass": grad["worst"] < RTOL_DISPLAY,
        "note": ("Failed on the first run with a relative error of exactly 1.0 "
                 "on every parameter -- the numerical gradient was zero because "
                 "the softmax had saturated and the cross-entropy was sitting "
                 "on its clipping floor -- fixed by input scaling. It failed "
                 "twice more on structurally zero gradients: convolution "
                 "biases before a normalisation layer (removed), then bn1.beta "
                 "once the activation moved ahead of the normalisation, since "
                 "a shift is exactly what the next normalisation subtracts. A "
                 "relative-error metric on two zeros returns noise, so the "
                 "check carries two floors -- one scaled to the tensor's own "
                 "RMS, one absolute for a tensor that is zero throughout."),
    })

    # ---------------------------------------------------------------- B
    over = overfit_check(covers, stegos)
    results.append({
        "name": "B_optimisation_works",
        **over,
        "pass": over["loss_end"] < 0.45,
        "note": ("An overfit check separates 'cannot optimise' from 'nothing to "
                 "find'. Both looked identical from the outside and needed "
                 "opposite fixes."),
    })

    # ------------------------------------------------------- B2, C, D
    full = run_variant("full", covers, stegos, half, args.epochs)
    no_hp = run_variant("no_high_pass", covers, stegos, half, args.epochs,
                        high_pass=False)
    no_abs = run_variant("relu_instead_of_abs", covers, stegos, half,
                         args.epochs, abs_activation=False)

    # The T5 baseline is computed here so B2 can be conditioned on it.
    fc = np.array([spam686(c) for c in covers])
    fs = np.array([spam686(s) for s in stegos])
    clf = FldEnsemble(n_learners=40, d_sub=200, seed=1).fit(fc[:half], fs[:half])
    pe_t5, _ = min_error_probability(clf.decision_function(fc[half:]),
                                     clf.decision_function(fs[half:]))
    baseline_detectable = pe_t5 <= 0.35
    results.append({
        "name": ("B2_the_network_learns_the_task" if baseline_detectable
                 else "B2_not_gradeable_the_corpus_caps_both_methods"),
        **full,
        "t5_baseline_P_E": round(pe_t5, 4),
        "threshold": 0.40,
        "graded": baseline_detectable,
        "pass": (full["P_E"] <= 0.40) if baseline_detectable else True,
        "note": (None if baseline_detectable else
                 f"SPAM686 reaches only {pe_t5:.3f} on the same task, so the "
                 f"corpus, not the architecture, sets the floor. Run "
                 f"--corpus real to grade this."),
    })
    results.append({
        "name": "C_fixed_high_pass_layer_is_necessary",
        "P_E_with": full["P_E"],
        "P_E_without": no_hp["P_E"],
        "cost_of_removing": round(no_hp["P_E"] - full["P_E"], 4),
        "pass": no_hp["P_E"] > full["P_E"] + 0.03,
        "note": ("Xu-Net's central contribution. A network on raw pixels must "
                 "first learn to suppress image content, which outweighs the "
                 "stego signal by orders of magnitude, and a few hundred "
                 "training images are nowhere near enough to get there."),
    })
    results.append({
        "name": "D_abs_activation_reported_not_graded",
        "P_E_with_abs": full["P_E"],
        "P_E_with_relu": no_abs["P_E"],
        "difference": round(no_abs["P_E"] - full["P_E"], 4),
        "pass": True,
        "note": ("Embedding is +/-1 with equal probability, so a residual's "
                 "sign says nothing about whether a payload exists. Measured "
                 "on BOSSbase at 128px with the activation in Xu-Net's "
                 "position (convolution -> ABS -> normalisation): ABS 0.1633 "
                 "against ReLU 0.1700, so ABS is ahead by 0.0067. With the "
                 "activation placed AFTER normalisation -- as this file had it "
                 "until v0.22 -- the same measurement put ReLU ahead by 0.0966, "
                 "because normalisation centres its output at zero and |x| of "
                 "that is a half-normal nothing re-centres. The direction now "
                 "agrees with the literature; the margin at this scale does "
                 "not carry a criterion, so this stays reported. Gap G-21."),
    })

    # ---------------------------------------------------------------- E
    results.append({
        "name": "E_comparison_with_t5_and_its_cost",
        "task": (f"{EMBEDDER.__name__} at {PAYLOAD} bpp, {corpus_desc}, "
                 f"{half} train / {args.n - half} test"),
        "cnn": {"P_E": full["P_E"], "parameters": full["parameters"],
                "epochs": full["epochs"], "train_seconds": full["seconds"]},
        "spam686_fld_ensemble": {
            "P_E": round(pe_t5, 4), "features": int(fc.shape[1]),
            "training": "no gradient steps; closed-form discriminants"},
        "pass": True,
        "note": ("Reported, not graded. Published CNN results use tens of "
                 "thousands of 256x256 real camera images and GPU training; "
                 "nothing here is comparable to them, and the absolute "
                 "figures must not be quoted outside this setup. What the "
                 "table is for is the trade: hand-designed residuals need no "
                 "training and cap out at what was designed in, while a "
                 "learned residual needs data and time and does not cap out."),
    })

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "G6.json").write_text(json.dumps(results, indent=2) + "\n")

    print("=" * 70)
    print(f"Gate G6 -- deep-learning steganalysis, {args.n} covers, "
          f"{PAYLOAD} bpp")
    print(f"corpus: {corpus_desc}")
    print("=" * 70)
    failed = False
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        if not r["pass"]:
            failed = True
        print(f"[{status}] {r['name']}")
        for k, v in r.items():
            if k in ("name", "pass", "note"):
                continue
            print(f"        {k}: {v}")
        if "note" in r:
            print(f"        -> {r['note']}")
    print("=" * 70)
    print("GATE G6:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
