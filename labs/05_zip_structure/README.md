# Lab 05 -- ZIP structure: three places the format leaves room

| | |
|---|---|
| Domain | container |
| Algorithm | pseudo-encryption / archive-comment / unreferenced-gap |
| Detectors | `zip_pseudo_encryption`, `zip_archive_comment`, `zip_unreferenced_gap`, `zip_header_disagreement` |
| Evidence ceiling | E4 for comment and gap, E3 for pseudo-encryption |

## The shared root cause

ZIP is read backwards. A reader locates the end-of-central-directory record,
walks the central directory, and opens only what the central directory
mentions. Anything the central directory declines to mention is invisible
*by design*, not by oversight.

The detector therefore does the opposite: it walks local file headers
forwards and reconciles the two views against the file's actual length.

## Three variants

**(a) Pseudo-encryption.** Set general-purpose flag bit 0 without encrypting
anything. Every GUI archiver prompts for a password it will never verify,
and most analysts move on. The data was never protected; it was labelled.

Detection is decisive rather than statistical: take the stored bytes and try
to inflate them. If raw deflate succeeds, there is no encryption, whatever
the flag says.

**(b) Archive comment.** Up to 65535 bytes after the EOCD record.
Structurally legal, never displayed by default.

**(c) Unreferenced gap.** Bytes between the last local entry and the central
directory. No structure points at them, so no reader reads them. The lab's
embedder advances the EOCD's central-directory offset accordingly -- a
hiding place that breaks the archive is not a hiding place, and the test
asserts the archive still opens and passes `testzip()`.

## Reproduce

```bash
python3 -m pytest tests/test_labs_a.py -q
```

## What it teaches

When a format has two descriptions of its own contents, compare them. The
same pattern recurs at every layer: local versus central here, `IHDR` versus
`IDAT` in lab 04, declared versus decoded scan length in lab 06.
