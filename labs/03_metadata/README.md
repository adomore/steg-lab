# Lab 03 -- Metadata as a carrier

| | |
|---|---|
| Domain | metadata |
| Algorithm | text-chunk / comment-segment payload |
| Detector | `metadata_profile` |
| Measured FPR | 0/100 PNG, 0/100 JPEG on same-source clean covers |
| Evidence ceiling | E4 when the field decodes, E2 when it only looks wrong |

## The trick

Metadata is a designed-in, standards-blessed, effectively unbounded place to
put bytes that no decoder validates and no viewer displays. PNG offers
`tEXt`, `zTXt` and `iTXt`; JPEG offers `COM` and sixteen `APPn` slots. Both
survive most copy, upload and resize operations untouched.

`zTXt` is the interesting one: the payload is deflated before storage, so a
naive string search finds nothing and an entropy scan sees compressed noise
where a caption should be.

## Why the FPR is the whole problem

Every real photograph carries metadata. A camera writes kilobytes of it.
So "this file has metadata" is worth nothing, and the useful statement is
"this file has metadata that does not look like the metadata this source
produces".

That is a claim about a source, which means it cannot be made without first
characterising the source. A profile built on the wrong camera, the wrong
export pipeline or the wrong social platform is not a profile.

## The detection

Three signals, combined:

- length beyond what a caption plausibly needs
- entropy above what prose reaches (base64 of arbitrary bytes lands near
  6.0 bits/byte; English text sits near 4.2)
- a field that decodes cleanly as base64

Only the third yields E4, because only the third produces a payload.

## Reproduce

```bash
python3 -m pytest tests/test_labs_a.py -q
```

## What it teaches

This is the first lab where the threshold is not a property of the format
but of the source. Everything in T4 and T5 is that problem, scaled up.

---

[Chinese version](README_zh.md)
