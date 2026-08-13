# T0 -- Problem definition and threat model

> Gate: **G0** -- `python3 gates/g0_wardens.py` -- PASSED

## 0.1 The prisoners' problem

Simmons' 1983 framing is still the right one. Alice and Bob are in separate
cells. They may exchange messages, but every message passes through a warden
who will cut the channel the moment she suspects a hidden conversation.

The essential move is that the adversary is defined by **what she is allowed
to do to the channel**, not by how clever she is. That distinction organises
everything downstream, because a technique that defeats one warden class can
be irrelevant against another.

| Warden | Capability | What it costs the sender |
|---|---|---|
| Passive | observes, forwards unchanged | must be undetectable |
| Active | modifies benignly, does not know a payload exists | must be robust |
| Malicious | modifies deliberately, may substitute content | must be authenticated |

## 0.2 Three boundaries worth keeping straight

**Steganography** hides the existence of a message. **Cryptography** hides
its content. **Watermarking** hides an ownership mark that is meant to
survive attack rather than to stay unnoticed. **Covert channels** move
information through a system resource never intended to carry it.

The practical consequence: a steganographic channel provides *no*
confidentiality and *no* integrity. If the payload matters, it must carry
its own encryption and its own authentication. Section 0.5 measures what
happens when it does not.

## 0.3 What "secure" means formally

Cachin's model treats detection as a hypothesis test between the cover
distribution `P_C` and the stego distribution `P_S`. A system is
**ε-secure** when the relative entropy between them is bounded:

```
D(P_C || P_S) <= epsilon
```

Perfect security is `epsilon = 0`: the two distributions are identical, so
no test -- of any computational power -- beats coin flipping. Hopper,
Langford and von Ahn give the complexity-theoretic counterpart, where
security holds against computationally bounded adversaries and rests on the
existence of a sampling oracle for the cover source.

The practical reading matters more than the formalism. Everything an
embedder does to a carrier is a *deviation from the cover source's own
distribution*, and every detector is an estimator of that deviation. Which
is why the hardest problem in this field is not detection but knowing what
the cover distribution actually was -- the theme that returns in T4 as cover
source mismatch.

## 0.4 The three-way trade-off

Capacity, imperceptibility and robustness cannot be maximised together:

- raising **capacity** at fixed carrier size increases the deviation from
  `P_C`, lowering imperceptibility
- raising **robustness** requires redundancy, which consumes capacity
- maximising **imperceptibility** pushes towards embedding so little that
  the channel stops being useful

Real systems pick a corner. steghide picks imperceptibility and capacity and
abandons robustness entirely -- which is exactly what G0 measures below.

## 0.5 Gate G0: the wardens, measured

The claim "three warden classes matter operationally" is not left as an
assertion. `gates/g0_wardens.py` builds one reproducible instance of each.

### Criterion A -- passive warden

Twelve trials, sequential LSB payload, PNG round-trip through a real
encoder. **Maximum bit error rate: 0.0.** The payload arrives byte-identical,
so the warden's only available move is detection. That is what makes the
passive setting the domain of statistical steganalysis.

### Criterion B1 -- active warden versus LSB

Twelve trials, JPEG recompression at quality 90, no knowledge of whether a
payload exists.

| statistic | value |
|---|---|
| median BER | 0.498 |
| minimum BER | 0.473 |
| maximum BER | 0.510 |
| threshold | > 0.45 |

A bit error rate at 0.5 means the recovered bits carry no information at
all. One lossy recompression -- the sort every messaging app performs
automatically -- destroys the channel completely.

### Criterion B2 -- active warden versus steghide

Twelve trials. Control extraction (no warden) succeeds first, otherwise the
experiment would prove nothing. Then the warden decodes and re-encodes at
quality 90.

**Extraction failures: 12/12. Payload survivals: 0.**

### The asymmetry worth noticing

B1 and B2 both report total loss, but they are not the same result. LSB
degrades *gracefully*: the bits are still there, they are simply wrong about
half the time, and error-correcting codes could in principle claw some back.
steghide fails *catastrophically*: it has no error correction, so a single
altered coefficient breaks the extraction entirely and the receiver gets
nothing rather than a corrupted something.

The design lesson: robustness is not a property you get by choosing a good
embedding domain. It is a property you must engineer, and almost no
general-purpose steganography tool engineers it.

### Criterion C -- malicious warden

Twelve trials. The warden knows the channel convention but not the message.
It overwrites the payload with its own and forwards.

**Forgeries accepted: 12/12.**

The receiver extracts the substituted message and has no way to notice. This
is the concrete demonstration of section 0.2: steganography hides existence,
not integrity. Confidentiality and authentication must come from the
payload's own cryptography, applied *before* embedding.

## 0.6 What this means for the analyst

Reading the table from the detection side rather than the embedding side:

1. Against a **passive** channel, structural and statistical detection are
   the entire game, and the A-group labs are where that starts.
2. Against an **active** channel, absence of a payload proves nothing. A
   recompressed image may have carried one that no longer exists. Reports
   must say which was tested.
3. A **malicious** warden is a capability the analyst also has. Destroying a
   suspected channel is cheap and often the correct operational answer, but
   it is not evidence, and it destroys the artefact. Decide which you are
   doing before you do it.

## 0.7 Further reading

Simmons (1984) on the prisoners' problem; Cachin (1998, 2004) on
information-theoretic security; Hopper, Langford and von Ahn (2002) on
complexity-theoretic steganography; Fridrich, *Steganography in Digital
Media* (2009), chapters 1-3 and 6.

---

Next: [T1 -- Carriers and embedding domains](T1_carriers_and_domains.md) |
[Chinese version](T0_threat_model_zh.md)
