# Using the tools without being misled by them

Every parser in this repository is cross-validated against an external tool --
pngcheck, djpeg, tshark, ffmpeg, mtools, debugfs, ntfscat. Doing that produced
a second, unplanned result: a list of the specific ways each tool's output can
be read wrong. This document is that list.

It is not a tool tutorial. The manuals cover invocation. What follows is what
the manuals do not say, measured on this repository's own carriers.

## The one rule

**A tool's silence is not evidence of absence, and its output is not evidence
of presence.** Both directions need a measured baseline on same-source clean
carriers before anything reaches E3, which is the same rule the evidence ladder
enforces on this repository's own detectors. A tool is not exempt because
somebody else wrote it.

## Exit codes: what they actually mean

Measured, not quoted from manuals.

| tool | condition | exit |
|---|---|---|
| `pngcheck` | clean PNG | 0 |
| `pngcheck` | PNG with appended data | **2** |
| `steghide extract -q` | correct passphrase | 0 |
| `steghide extract -q` | wrong passphrase | 1 |
| `steghide extract -q` | clean carrier, any passphrase | **1** |

Two traps here.

`pngcheck` returns 2 for **any** structural problem. Appended data, a bad CRC
and a genuinely corrupt file all produce the same code. A script that branches
on the exit status learns that something is wrong and nothing about what.
Parse the message, or use the structural labs, which distinguish these cases
because they were written to.

`steghide` returns 1 for a wrong passphrase **and** for a carrier with nothing
in it. This is the difference between "the password is wrong" and "there is no
payload", and the exit code does not carry it. What does carry it: on success
the output file is created, on failure it is not. Test for the file.

## Tools that cannot report what they do not do

The most dangerous output is a clean run from a tool that never examined the
thing you care about.

**`zsteg`** covers PNG and BMP LSB in various bit orders and channel
combinations. It is a good triage tool for LSB *replacement*. It has nothing to
say about LSB *matching* -- and it does not say so. A quiet zsteg on a carrier
holding a matching payload is a correct run with no finding, which reads
identically to a correct run on a clean file. T5 measures what matching
actually needs: a trained classifier, `P_E` 0.125 on real covers against
structural detectors at 0.405.

**`steghide`** detects steghide. That is a statement about a program, not about
a carrier. A steghide-negative JPEG can hold Jsteg, F5, nsF5 or an appended
archive.

**`exiftool`** parses the metadata containers it knows. A payload in a private
PNG chunk that is not a text chunk, or in a JPEG APPn segment exiftool does not
model, produces no output and no warning. Lab 03 and lab 04 exist because
metadata triage and structural accounting are different operations.

**`binwalk`** finds embedded file signatures. On this repository's clean
synthetic JPEG it reports zero lines, which is the good case; on real
photographs it produces false leads regularly, because a signature is four
bytes and images contain many four-byte sequences. Every binwalk hit needs its
offset checked against the container's own structure before it means anything.

## Cleaning a carrier is not the same as reading it

`exiftool -all=` removes the metadata blocks exiftool understands. Measured on
a PNG carrying a payload in a `tEXt` chunk: lab 03's detector reports **E1
before and E0 after**, and the file shrinks by 48 bytes. The evidence is gone.

That is a correct outcome for a cleaning tool and a catastrophic habit in an
examination. Every command here that modifies a file belongs on a **copy**, and
the checklist's first item -- hash the original before touching it -- exists
for exactly this.

A note on how that measurement was made, because the first attempt was wrong.
Checking for the payload *string* in the file found nothing either before or
after, since lab 03 encodes what it embeds -- so the check "confirmed" a claim
it had never tested. Searching raw bytes for a payload you do not know the
encoding of proves nothing in either direction. The detector is the instrument;
`grep` is not.

## Where the tools disagree with each other, and who is right

Cross-validation turned up real disagreements. Each was resolved by finding a
third reference that neither implementation could influence.

**`djpeg` wording is not portable.** IJG's djpeg and libjpeg-turbo's djpeg
print different verbose text for the same file. A check that greps for one
implementation's phrasing reports a working tool as broken -- which happened
here, on Kali, and is why `scripts/verify-toolchain.sh` now decodes a file and
inspects the result instead of matching strings.

**Two implementations agreeing proves nothing if they share an assumption.**
This repository's baseline and progressive JPEG decoders once agreed with each
other and were both wrong, and the encoder round-trip passed because encode and
decode shared the error. What settled it was computing the DC coefficient
directly from the decoded pixels -- a reference neither decoder could influence.
When two tools agree, ask whether they could fail together.

**A raw string search can miss a payload that is present.** NTFS replaces the
last two bytes of every 512-byte sector inside an MFT record with an
update-sequence number. A resident alternate data stream spanning a sector
boundary is therefore broken in the raw image and perfect through a driver:
measured, a 480-byte stream matched for 414 bytes and stopped. `grep` over a
disk image is not a reliable test for content.

## Order of operations

The checklist has this in full; the tool-specific version is short.

1. **Hash the original.** Everything after this happens on a copy.
2. **Structural accounting**, which is deterministic: does every byte have a
   reason to exist? `pngcheck -v`, `djpeg -verbose -verbose`, `unzip -l`,
   `binwalk`, plus the A-group labs for the cases those miss.
3. **Metadata**, which is separate: `exiftool -a -G1 -s`.
4. **Only then signal-layer triage**, which needs a threshold, which needs a
   baseline measured on clean carriers from the same source.

Running step 4 first is the most common way to get a confident wrong answer,
because a statistical detector always returns a number.

## What to write down

For every tool invocation that appears in a report: the tool, its **version**,
the exact arguments, and what it examined. `steghide 0.5.1` and
`steghide 0.6` are different programs. `binwalk` changed its output format
between major versions. A finding that cannot be reproduced from the report is
not a finding.

And record what was **not** run. Absent coverage is not absent risk, and a
report that does not say what it skipped implies it skipped nothing.

---

[Chinese version](TOOL_PRACTICE_zh.md)
