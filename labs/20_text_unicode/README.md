# Lab 20 -- Text carriers: the false positives are the difficulty

| | |
|---|---|
| Domain | text |
| Algorithms | zero-width, variation-selector, trailing-whitespace |
| Detectors | `text_zero_width`, `text_variation_selectors`, `text_trailing_whitespace` |
| Measured FPR | 0/8 on a legitimate multilingual corpus |
| Evidence ceiling | E4 -- all three channels are keyless |

## What makes text different from every carrier before it

The hiding places in a PNG, a JPEG, a WAV or a palette were bytes that nothing
legitimate needed. A chunk nobody registered. A segment no decoder reads.
Silence that is exactly zero. Finding them was work; once found there was
nothing to argue about.

**The characters used to hide in text do real linguistic work.** ZERO WIDTH
NON-JOINER separates Persian and Urdu morphemes. ZERO WIDTH JOINER builds emoji
sequences and Devanagari conjuncts. VARIATION SELECTOR-16 is what makes an
emoji render as an emoji rather than as a dingbat.

A detector that flags every invisible character reports every multilingual
document ever written. On the corpora that actually matter, that is a 100%
false-positive rate.

So the lab's content is not "find the invisible characters". It is: given that
they are everywhere and mostly innocent, what distinguishes carrying from
writing?

## Three contextual signals

**Runs.** Orthography places one joiner between two letters. Payload bits
arrive consecutively, so a run of three or more has no reading in any script.

**Script context.** A ZWNJ between two ASCII letters has no orthographic job,
because no script written in ASCII uses one. This is the signal that survives a
careful adversary -- see below.

**Selector range.** VS15 and VS16 are presentation selectors and are
ubiquitous. VS17 upward exist for Ideographic Variation Sequences and are
meaningless after a non-CJK base -- and they carry a whole *byte* each, which
makes that channel eight times denser than the zero-width alphabet.

## The careful adversary, and which signal catches it

The naive embedder writes its bits as one contiguous block: 104 zero-width
characters in a single run, which the run-length signal finds instantly and
which nobody competent would produce.

The careful one distributes single bits between letters, so the longest run is
1 and the run-length signal reports nothing at all:

| adversary | longest run | runs over threshold | runs between ASCII letters | verdict |
|---|---|---|---|---|
| contiguous | 104 | 1 | 0 | detected |
| **spread** | **1** | **0** | **48** | **detected** |

Two independent signals, and the adversary who defeats one walks into the
other. That is the argument for having both rather than tuning one.

## Legitimate corpus: 0/8

| text | zero-width chars | verdict |
|---|---|---|
| English prose | 0 | E0 |
| Persian with ZWNJ | 3 | E0 |
| Emoji ZWJ sequences plus VS16 | 2 | E0 |
| Devanagari with ZWNJ and ZWJ | 2 | E0 |
| CJK with ideographic variation sequences | 0 | E0 |
| Persian, second sample | 2 | E0 |
| Latin with diacritics | 0 | E0 |
| URL preceded by a BOM | 1 | E0 |

Every one of these contains invisible characters doing their jobs, and none of
them is reported.

## Trailing whitespace needs the same treatment

Counting lines that end in whitespace flags ordinary documents: editors leave
stray spaces, and Markdown's hard-break convention is two trailing *spaces*.

Two things separate an encoding from an accident. **Tabs** -- prose essentially
never ends a line with one, but a space/tab alphabet needs them for every 1
bit. And **contiguity** -- a payload occupies a prefix of consecutive lines,
because that is the order it is written in.

| text | trailing tabs | longest run | verdict |
|---|---|---|---|
| SNOW-style payload | 22 | 32 | detected |
| Markdown hard breaks | 0 | 1 | E0 |
| Editor leftovers | 0 | 1 | E0 |

## All three reach E4

None of these channels is keyed. The zero-width alphabet is fixed, the
selector block maps directly onto byte values, and the whitespace encoding
reads off line endings in order. Confirm the presence and the payload comes
with it -- the same property that let labs 13 and 10 reach E4, arriving for the
same reason.

## Reproduce

```bash
python3 -m pytest tests/test_labs_g.py -q
```

## What it teaches

Every other lab could treat its false-positive baseline as a property of the
*source*. Here it is a property of the *language*: a detector calibrated on
English prose and applied to Persian is not slightly wrong, it is useless. The
evidence ladder's demand for a same-source baseline reads, in this domain, as a
demand for the same script.

---

[Chinese version](README_zh.md)
