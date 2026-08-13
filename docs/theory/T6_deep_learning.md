# T6 -- Deep-learning steganalysis

> Gate: **G6** -- `python3 gates/g6_deep_learning.py` -- PASSED

## 6.1 Replacing the designed residual

T5 ended with hand-designed residuals: one difference operator, 686 features,
an ensemble on top. T6 replaces the design step with training. What survives
that replacement is the interesting question, and the way to answer it is to
build the network and then take pieces off it.

`steganalysis.cnn` is about 8,200 parameters of numpy -- convolutions via
im2col, batch normalisation, hand-written backward passes, SGD with momentum.
No framework, no GPU. The backward passes are checked against central
differences in gate G6 rather than trusted.

## 6.2 The three architectural claims

**The first layer is a fixed high-pass filter, not learned.** This is Xu-Net's
central contribution. A network on raw pixels must first learn to suppress
image content, which outweighs the stego signal by orders of magnitude. Handing
it the KV kernel starts it where the residual already is.

**The activation after the first convolution is |x|.** Embedding is symmetric:
+1 and -1 are equally likely, so the sign of a residual says nothing about
whether a payload exists.

**Pooling is average, never max.** The stego signal is low-amplitude and spread
across the carrier. Max pooling keeps the loudest response in each window,
which keeps image content and discards the payload.

## 6.3 What the gate measured

On BOSSbase, 300 covers centre-cropped to 64px, LSB replacement at 1.0 bpp,
150 training pairs and 150 test pairs:

| criterion | synthetic 64px | **BOSSbase 128px** |
|---|---|---|
| gradients vs central differences | 7e-08 | 4e-06 |
| optimisation works (memorise 32 samples) | 0.786 -> 0.184 | 0.800 -> 0.253 |
| CNN test P_E | 0.419 | **0.163** |
| **fixed high-pass layer removed** | 0.488 (costs 0.069) | **0.493 (costs 0.330)** |
| ABS replaced by ReLU | 0.413 | 0.170 |
| SPAM686 + ensemble, same split | 0.425 | **0.120** |

**The high-pass claim is confirmed, and on real covers it is not subtle.**
Removing the fixed first layer takes the network from P_E 0.163 to 0.493 --
from a working detector to *chance*, on an architecture otherwise identical.
Xu-Net's contribution is not a refinement; without it this network does not
work at all.

**The ABS claim replicates, once the layer is in the right place.** ABS
measures 0.163 against ReLU's 0.170 -- ahead, but by 0.0067, which is too small
to carry a criterion at this scale. So the gate reports it rather than grading
it. Section 6.5 is about how that number was arrived at, because for two
sessions it had the opposite sign.

**And the hand-designed features still win.** SPAM686 with an ensemble reaches
P_E 0.120 against the CNN's 0.163, on the same carriers and the same split,
with no gradient steps at all. On 150 training pairs of 128px crops that is the
expected ordering and it is worth stating plainly: a learned residual has to
earn its keep with data, and here it has not been given enough.

## 6.4 Where the activation goes

Xu-Net specifies convolution -> ABS -> normalisation. This chapter had
convolution -> normalisation -> ABS for two sessions, and the consequences are
worth the space.

Batch normalisation centres its output at zero. Taking |x| of a zero-centred
distribution gives a half-normal with mean about +0.8, and with the
normalisation already spent there is nothing to re-centre it before the next
convolution. Measured with the layers in the wrong order, at 128px on
BOSSbase: ABS 0.2333 against ReLU 0.1367, so ReLU won by 0.0966 -- four times
the gap seen at 64px, and a difference that *grows* with scale normally ends
the "not enough statistical power" defence.

The gradient check settles it independently. With the activation after
normalisation the worst relative error is 5e-02; with it before, 5e-09. The
reason is exact: |x| has a kink at zero and a normalised activation
concentrates precisely there, so the old arrangement was not cleanly
differentiable where it mattered.

Correcting the order changed the sign of the ABS effect -- and improved every
other number in the chapter. The network went from P_E 0.2333 to 0.1633 and
the measured cost of removing the high-pass layer grew from 0.26 to 0.33. A
misplaced layer had been depressing results that all looked plausible.

The transferable part is not the bug. It is that **a result contradicting
published work is worth more as a lead than as a finding.** "ABS does not help"
was publishable-looking, was wrong, and would have buried the defect that
caused it. What made the difference was insisting on a mechanism: "ABS does not
help" is not falsifiable, "ABS after normalisation destroys the centring" is,
and testing it took one experiment.

## 6.5 Two failures that looked identical from outside

Both are worth more than the results above.

**The network could not learn at all.** Every figure came back at chance and
the training loss sat at ln(2) = 0.6931. The obvious reading was that the task
had no signal. It was wrong: activations collapsed through the layers -- the KV
response on scaled input is small, He initialisation shrinks it again at each
convolution, and by the global average pool no usable gradient reached the
early layers. Batch normalisation fixed it. This is why every published
architecture in this family has normalisation between layers, and it is worth
knowing as a fact about optimisation rather than a line in a diagram.

**Then it still could not.** 32 samples at batch size 32 is one optimisation
step per epoch, so 60 epochs was 60 steps. At batch size 8 and a higher
learning rate the same network memorises the same data in 600.

An **overfit check** separates "cannot optimise" from "nothing to find". They
present identically -- everything at chance -- and need opposite responses. It
is now criterion B, ahead of every result that depends on it.

## 6.6 The trade, stated plainly

Hand-designed residuals need no training and cap out at what was designed in.
A learned residual needs data and time and does not cap out. On this corpus,
with these carrier sizes and this much compute, the designed residual is not
behind -- which is the honest summary of a numpy network on 160 synthetic
64x64 images, and says nothing about the method.

What transfers from this chapter is the ablation, not the score: the fixed
high-pass layer earns its place, measurably, on an otherwise identical network.

## 6.7 What comes after

SRNet removes the need for the fixed first layer by making the network deep
enough to learn the residual itself. The SCA variants feed selection-channel
knowledge -- an estimate of *where* embedding was likely -- to the network,
which is T3's cost function arriving from the other side. Both need scale this
chapter does not have.

## 6.8 Further reading

Xu, Wu and Shi (2016) for the fixed high-pass layer and the ABS activation;
Ye, Ni and Yi (2017) for Ye-Net and the truncated linear unit; Boroumand, Chen
and Fridrich (2019) for SRNet; Ioffe and Szegedy (2015) for batch
normalisation, which section 6.4 is a small rediscovery of.

---

Previous: [T5 -- Feature sets and ensemble classification](T5_feature_sets.md) |
Next: [T7 -- Forensic workflow and decision-making](T7_forensic_workflow.md) |
[Chinese version](T6_deep_learning_zh.md)
