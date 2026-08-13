# Lab 23 -- File slack: the payload does not travel with the file

| | |
|---|---|
| Domain | filesystem |
| Algorithm | file-slack |
| Detector | `fat_file_slack` |
| Measured FPR | 0/8 on freshly formatted volumes |
| Detection | 8/8; payload recovered byte-exact |
| Evidence ceiling | E4 |

## Slack

A filesystem hands out storage in clusters. A file of N bytes with C-byte
clusters leaves `C - (N mod C)` bytes inside its last cluster that belong to
its allocation and hold none of its content. Measured on a 16 MB FAT16 volume
with 4,096-byte clusters:

| file | size | clusters | slack |
|---|---|---|---|
| A.TXT | 11 | 1 | 4,085 |
| B.BIN | 5,000 | 2 | 3,192 |
| C.DAT | 8,192 | 2 | **0** -- exact fit |

## What changes when the carrier is a volume

Every carrier before this one was part of a file. Copy the file and the payload
comes along.

Slack is a property of the **volume**. Copy the file out and the payload stays
behind. Defragment and it moves or vanishes. That single fact reorders the
examination: **the evidence is the disk image, and a working copy of the files
is not a copy of the evidence.** An examiner who collected files rather than
imaging the volume has already destroyed this channel without knowing it.

## The twin, and it is not rare

Every other lab asked whether an anomaly is a payload. Here non-zero slack has
a second explanation that is not merely possible but *normal*.

Delete a file, write a smaller one into its cluster, and the old file's tail
survives in the new file's slack. Constructed and measured:

```
BIG.DAT  = "CONFIDENTIAL MEMO " x 220     -> written, then deleted
NEW.TXT  = "short\n"                      -> takes the same cluster
```

The detector reports 3,954 non-zero slack bytes at 3.5 bits/byte, and the
extracted content is:

```
ENTIAL MEMO CONFIDENTIAL MEMO CONFIDENTI
```

**A deliberate payload and a deleted file's tail produce the same finding.**
There is no statistic here that separates them, and inventing one would be
worse than admitting it: entropy does not, because both can be text or both can
be compressed; position does not, because both start at the top of the slack.

So the detector reports the finding and states both readings in its own claim
text. The analyst reads the recovered bytes and decides, which is the correct
division of labour -- and worth noticing, **the innocent explanation is often
the more valuable evidence.** Recovering the tail of a deleted confidential
memo matters more to most investigations than proving somebody used steg.

## Why the baseline is unusually strong here

`mkfs.vfat` zeroes clusters, so a freshly formatted volume has zero non-zero
slack -- measured 0 bytes across every file on 8 fresh volumes. That makes the
false-positive rate genuinely zero *on a fresh volume*, and it makes the
qualifier load-bearing: on a volume that has been in use, the baseline is
whatever the deletion history left, and it is not zero.

## Why FAT, and what is still missing

FAT is implemented because the whole chain can be verified inside this
repository: `mkfs.vfat` builds the volume, `mcopy` writes into it, and
`fsck.vfat` and `mdir` check the result -- so the geometry, the directory
entries and the file sizes are all measured against independent tools rather
than against this parser's own assumptions.

ext4 slack and NTFS alternate data streams need a mounted volume and privileges
this environment does not have. They stay recorded as gaps rather than being
approximated, because a lab that cannot verify itself is worse than no lab.

## Reproduce

```bash
python3 -m pytest tests/test_labs_j.py -q
```

## What it teaches

Ask what the carrier *is* before asking what is in it. Here the carrier is not
the file the payload appears to sit behind -- it is the volume, and the
acquisition method decides whether the channel exists at all by the time anyone
looks.

---

[Chinese version](README_zh.md)
