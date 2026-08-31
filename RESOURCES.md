# Resources

See [Tool practice](docs/TOOL_PRACTICE.md) for how each of these can mislead;
this section only says what they are for.

## Toolchain by layer

| Layer | Tools | Installed by |
|---|---|---|
| container triage | binwalk, foremost, bulk_extractor, file, xxd | apt |
| structural validation | pngcheck, djpeg, jpegtran, exiftool | apt |
| image steganography | steghide, outguess, zsteg, stegsolve, openstego | apt + gem + jar |
| password recovery | stegseek, stegcracker, john, hashcat | source / apt |
| ML steganalysis | aletheia, StegExpose | pip / jar |
| audio | sox, audacity, sonic-visualiser, ffmpeg | apt |
| network | tshark, zeek | apt |
| general | ImageMagick, Python scientific stack | apt + pip |

Gates G0 and G1 depend on `pngcheck`, `djpeg` and `steghide` specifically.
Without them the gates skip rather than fail, and the theory chapters lose
their evidence.

## Related work in this collection

- **stegseek-rs** -- a Rust reimplementation of the stegseek cracker
  covering the PRNG/selector subsystem, the S2K KDF, AES-128-CBC and the
  CVE-2021-27211 seed exploitation. A lab connecting to it was planned for P2
  as lab 17 and never built, which is why **E5 is the one rung of the ladder
  this repository defines but never reaches**: steghide passphrase recovery is
  the canonical E4-to-E5 transition, and here it stays a pointer.
- **sc-audit-lab** -- the smart-contract audit lab whose structure this
  repository borrows: gated theory, measured practice, EN/ZH lockstep,
  documentation checkers.

## Corpora

| Corpus | Content | Use |
|---|---|---|
| BOSSbase 1.01 | 10,000 grayscale 512x512, seven cameras | spatial-domain baseline |
| BOWS2 | 10,000 grayscale 512x512 | cover-source mismatch experiments |
| ALASKA2 | ~75,000 colour JPEG, multiple quality factors | JPEG-domain, realistic mixture |

Fetched by reference, never vendored: `bash scripts/get-corpora.sh`.

## Standards and frameworks

Steganalysis has no equivalent of the OWASP Top 10, so the framing comes
from forensics rather than from a vulnerability taxonomy:

- **NIST SP 800-86** -- integrating forensic techniques into incident
  response
- **ISO/IEC 27037 / 27042** -- identification and preservation of digital
  evidence; analysis and interpretation
- **SWGDE** -- image analysis and authentication guidelines
- **Daubert** -- the admissibility standard that makes "what is your error
  rate?" a question you will be asked under oath, and the reason the
  evidence ladder requires a measured baseline
- **MITRE ATT&CK** -- T1027.003 (obfuscated files: steganography) and
  T1001.002 (data obfuscation: steganographic) for the threat-intelligence
  anchor

Verify current identifiers against the sources before citing them in
anything evidential; this list was compiled at v0.1.0-P0.

## Literature

- Fridrich, *Steganography in Digital Media: Principles, Algorithms and
  Applications* (2009) -- the field's standard reference
- Simmons, "The Prisoners' Problem and the Subliminal Channel" (1984)
- Cachin, "An Information-Theoretic Model for Steganography" (1998, 2004)
- Hopper, Langford, von Ahn, "Provably Secure Steganography" (2002)
- Ker et al., "Moving Steganography and Steganalysis from the Laboratory
  into the Real World" (2013) -- the paper on why laboratory results do not
  transfer, and required reading before quoting any P_E figure

## Format specifications

- PNG: ISO/IEC 15948
- JPEG: ITU-T T.81
- ZIP: PKWARE APPNOTE.TXT

Read these in the original. Every hiding place in the A group is a
consequence of something the specification permits, and the specification
says so plainly.

---

[Chinese version](RESOURCES_zh.md)
