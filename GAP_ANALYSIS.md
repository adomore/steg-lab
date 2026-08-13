# Gap analysis

What is knowingly missing, and why. Items are tracked so they cannot be
quietly forgotten between sessions.

## Deviations from the confirmed outline

**D-1 -- lab 04 replaced.** The outline placed "NTFS alternate data streams
and filesystem slack" as A-group module 04. It needs a real mounted volume,
which the build environment did not have. Writing a module whose commands
cannot run is precisely the failure the `commands` checker exists to
prevent, so the slot went to `04_png_chunks` (private chunks, stale CRC,
`IHDR` height truncation) and filesystem slack moved to P3 with a hardware
prerequisite recorded. **Needs sign-off.**

## Open gaps

| ID | Gap | Severity | Plan |
|---|---|---|---|
| G-1 | CLOSED, all three filesystems. FAT file slack, ext4 file slack and NTFS alternate data streams all work through one lab interface, and none needs mount privileges: `mkfs.vfat`/`mtools`, `mkfs.ext4`/`debugfs` and `mkntfs`/`ntfscp` build and populate images as files. Cross-checked against mdir, debugfs and ntfscat respectively. A resident ADS reaches E4 with the payload; a non-resident one stops at E3, found but not recoverable from the MFT record alone | -- | -- |
| G-2 | CLOSED for images: `docs/cases/stegomalware.md` covers Duqu, Zeus/Zbot, Gatak/Stegoloader and Worok, organised by carrier with a detection-attribution table per section, sourced inline | -- | one narrative per remaining carrier group as those labs land |
| G-3 | No statistical detector of any kind | by design | P1, stage 3 |
| G-4 | CLOSED for G4 and G5: both gates now run on BOSSbase 1.01 (10,000 files, lag-1 correlation 0.931). Absolute figures are no longer provisional | -- | `--corpus real`. Still open for G3's security claim (G-15) and for ALASKA2 in the JPEG domain |
| G-18 | PARTLY CLOSED. Processing shift: `reference.PIPELINES` plus G5's `--all-pipelines`, already measured. Acquisition shift: `reference.second_source()` supplies scikit-image's sample photographs, which share no pipeline with BOSSbase -- different decades, sensors and scanners -- and ship with the toolchain, so G5 criterion D1 now includes a genuine second acquisition chain. Seven usable 256px crops makes the figure coarse; ALASKA2 would make it precise | low | ALASKA2, for sample size rather than for kind |
| G-15 | CLOSED on real BOSSbase: HILL+STC reaches P_E 0.344 against LSB matching's 0.198 at 0.4 bpp, a security gain of 0.146 | -- | gate G3 criterion E, graded |
| G-16 | PARTLY CLOSED and re-diagnosed. A searched, held-out-validated submatrix table now supplies h=8/10/12 at w=2, which removed the no-valid-path failures (21 of 72 random draws). It did NOT close the gap: among valid candidates best and median differ by ~1 point. The claim that a poor submatrix is the binding constraint was wrong -- see G-22 | low | `scripts/search-submatrices.py` regenerates the table |
| G-22 | CLOSED by keying the embedding path (F-37). The mechanism was raster-order traversal of spatially clustered costs: the trellis has a lookahead of h, texture is spatially clustered, so on a cover whose left half is flat the syndrome forces flips onto elements costing many times the median. `path_permutation` interleaves cheap and expensive elements and G3 criterion B now reads 5.98% at h=12, inside the published 5-10% band. Four earlier sub-hypotheses -- poor submatrices, cost dynamic range itself, wet paper codes, submatrix quality at other widths -- are all consequences of the ordering | -- | -- |
| G-17 | CLOSED: lab 14 detects F5 by calibration, 0/24 false positives, 12/12 at 0.10 bpp | -- | lab 14 |
| G-19 | CLOSED on real covers: on BOSSbase, removing the fixed high-pass layer takes the network from P_E 0.257 to 0.493 -- from working to chance. Hand-designed SPAM686 features still win at this scale (0.170) | -- | gate G6 |
| G-21 | RESOLVED. The contradiction was the layer order, not the claim. With the activation in Xu-Net's position (convolution -> ABS -> normalisation) the whole network improves -- P_E 0.2333 to 0.1633 on BOSSbase at 128px -- and the ABS effect changes sign: ABS 0.1633 against ReLU 0.1700, ahead by 0.0067, where the broken ordering had ReLU ahead by 0.0966. The direction now agrees with the literature. The margin is too small to carry a criterion at this scale, so G6's criterion D stays reported rather than graded, and says so with both numbers | -- | a larger carrier or more training pairs would settle the magnitude |
| G-20 | CLOSED. A population source model built from clean same-source carriers replaces the carrier-derived reference: AUC 1.000 discriminating F5 from its shrinkage-free variant, against 0.622-0.736 before. Named correctly on 12/12 F5 and 10/12 variant carriers, 0/12 clean false positives | -- | lab 14 `build_source_model` |
| G-5 | CLOSED: rustfmt installed, the crate reformatted, `cargo fmt --check` clean, all 8 Rust tests still pass | -- | the CI step can drop `continue-on-error` |
| G-6 | CLOSED: `decode_scan` handles progressive SOF2 -- spectral selection, successive approximation, all four scan types, per-scan Huffman tables and a scan-bounded bit reader. Validated by an identity: a baseline and a progressive encoding of one image share quantisation tables, so their coefficients must be bit-identical, and they are across three quality/size combinations | -- | -- |
| G-7 | CLOSED: `Ihdr.expected_raw_size` and `height_for_raw_size` handle Adam7's seven passes, and lab 04 detects and recovers height truncation on interlaced PNGs. Verified against a real interlaced carrier built by `png.encode_adam7`, because Pillow here ignores its `interlace` argument and would have silently tested the flat path | -- | -- |
| G-8 | CLOSED: run on Kali 2026.x, `verify-toolchain` reports 21 ok, 0 failed, 0 skipped with every reference implementation present and working. `dosfstools`/`mtools` added to the installer (lab 23 shipped without them); the stale note claiming stegseek is unpackaged in Kali corrected -- `apt install stegseek` works | -- | -- |
| G-9 | CLOSED, all carriers. Palette: lab 10 (EzStego), 0/24 false positives, E4. Audio: lab 18, RIFF parser cross-validated against the stdlib `wave` module, 0/16 at both bit depths. Text: lab 20, three channels, 0/8 on a legitimate multilingual corpus. Network: lab 21, three covert channels, 12/12 each against 0/12. Video: lab 22, temporal LSB consistency, 8/8 against 0/8, cross-validated against ffmpeg pixel-for-pixel | -- | -- |
| G-10 | The Rust sideline covers triage only; no statistical kernels | by design | P2 |
| G-11 | CLOSED. Sample Pair Analysis implemented from Dumitrescu, Wu and Wang (IEEE TSP 51(7), 2003), equation (18), and registered in DETECTORS. Synthetic covers, true p against estimate: 0.00->0.018, 0.05->0.048, 0.10->0.091, 0.20->0.208, 0.40->0.391; real photographs, mean error +0.008 to +0.020 against the 0.023 the paper reports. Correctly flat on LSB matching (0.020 clean, 0.024 at 0.4 bpp), which is the same required failure as RS and Weighted Stego | -- | -- |
| G-12 | ANSWERED: it was the corpus, not the implementation. Calibrated HCF-COM against LSB matching, AUC at 0.25/0.5/1.0 bpp -- synthetic covers 0.531/0.540/0.510, real photographs 0.543/0.565/**0.705**. The two-dimensional adjacency form Ker actually specifies adds a further increment (0.587/0.667/0.735) but is not the main effect. Calibration by down-sampling assumes natural-image statistics; the synthetic corpus does not have them, which is the same limitation that cost the statistical detectors their low-payload sensitivity in F-17 | low | still below the bar for the registry; a larger real corpus would fix the sample size |
| G-13 | CLOSED in P2: SPAM686 + FLD ensemble reaches P_E 0.140 vs LSB matching | -- | gate G5 |
| G-14 | CLOSED in P2b: baseline entropy encoder with optimal Huffman tables, round trip coefficient-exact | -- | `scripts/verify-jpeg-encoder.py` |

## Findings that cost real debugging time

Recorded because they will recur.

**F-1 -- PNG property bits.** The private bit is the second type letter, not
the third; the third is reserved and must be uppercase. The reference parser
had this wrong. Caught by gate G1 criterion C, which located the chunk
correctly and classified it incorrectly. Fixed on both the Python and Rust
sides, with the test duplicated in both.

**F-2 -- byte accounting cannot see post-scan padding.** A JPEG scan has no
declared length. Padding containing no `0xFF` is absorbed by the scan walk
and is genuinely undetectable structurally. This required a baseline
Huffman decoder, not a parser fix. The first implementation reported
nothing, correctly.

**F-3 -- truncated chunks are not CRC failures.** The Rust/Python
differential test disagreed on a deliberately truncated PNG. Python was
recording the truncated chunk as a CRC mismatch, which upgrades "damaged in
transit" into "edited after writing" -- a much stronger claim the bytes do
not support. Both sides corrected.

**F-4 -- libjpeg de-zigzags quantisation tables.** `DQT` stores zig-zag
order; libjpeg reports natural order after `jpeg_read_header`. Comparing
without `jpeg_natural_order` yields 64 spurious differences per table.

**F-31 -- the fix I was most confident about was aimed at the wrong thing.**
G-16 was carried for three sessions as "random submatrices are the binding
constraint", on the strength of a 3.5x mean-to-best spread on real covers. A
search settled it: among submatrices that produce a valid trellis at all, best
and median differ by about one percentage point, while clamping the cost range
from 60x to 7.5x moves the gap from 533% to 64%. The spread that looked like
evidence about matrices was mostly evidence about how a wide cost distribution
magnifies a single forced expensive flip. The table still earned its place --
it removes a one-in-three failure rate -- but the diagnosis it was built on was
wrong, and the search that confirmed the table is what disproved the reason for
building it.

**F-69 -- lockstep was enforced by file existence, which is not lockstep.**
The twins checker verified that every English document had a Chinese sibling
and stopped there. Two documents can both exist and disagree: a section added
on one side, a measured table updated in English and left stale in Chinese.
Both have happened in this repository's gap rows, and both were invisible
until somebody read the two files side by side.

The checker now compares the sequence of heading LEVELS -- not their text,
which is translated by design -- and the table row counts, exactly rather than
within a tolerance. The tolerance mattered: at +/-1 a deliberately dropped
table row stayed green, and dropping one row is the commonest drift there is.

Tightening it immediately produced a false positive, which is the part worth
recording. T6's Chinese text discusses `|x|` having a kink at zero, and a row
test that looks only for a leading pipe counted that paragraph as a table row
-- reporting two identical tables as drifted. **A checker's own false positive
is worse than the drift it looks for, because it trains people to override
it.** Row detection now requires a closing pipe and at least two cells.

The checker's behaviour is now tested in `tests/test_check_docs.py`, including
the shapes that must not fire: mathematical notation in prose, `#` comments
inside code fences, and translated heading text.

**F-68 -- an architectural fix invalidated a hyperparameter tuned for the old
architecture.** Correcting the ABS ordering (F-56) improved every measured
figure on real covers -- P_E 0.233 to 0.163 on BOSSbase at 128px. It also
broke gate G6's overfit check, which reached loss 0.173 under the old ordering
at lr 0.05 and only 0.488 under the corrected one. Moving the activation ahead
of the normalisation changes the scale of what reaches the next layer, and the
effective step size moves with it; lr 0.15 restores convergence at 0.224, and
0.30 diverges.

The failure surfaced two sessions after the change, on a routine re-run of
every gate, because nothing else exercises that code path. What caught it was
the shape of the criterion rather than diligence: criterion B trains to a
target and fails if it misses, so a slower architecture fails it. A criterion
that reported the final loss without a threshold would have recorded 0.488 as
a number and stayed green.

**F-67 -- the pipeline covered nine labs out of seventeen, and the capstone
could not report it.** Every carrier family added after `steganalysis/pipeline`
was written -- palette, audio, text, network, video, three filesystems -- was
never wired into it. `container_kind` knew PNG, JPEG and ZIP; everything else
fell to an `unknown` branch that ran the PNG/JPEG structural labs. Measured: a
WAV holding a 2,000-byte payload went through the pipeline as **E1** while lab
18 alone reached E4 on the same file.

Gate G7 kept passing throughout, because its trial builder only ever produced
carriers from the three domains the pipeline knew. **A blind test cannot report
a gap it never presents.** The capstone now draws from all thirteen recipes
across nine domains, and reports 34/40 with zero over-claims.

Three further defects surfaced only once the routing existed, each invisible
while the carriers were unreachable:

  * lab 01 reported E1 for any container whose end it could not compute, which
    flagged every clean WAV and AVI the moment they were routed to it.
    Inapplicability is not a finding; it now returns an empty report.
  * lab 20 was written against `str` while the pipeline hands every lab
    `bytes`, so the text stage produced nothing at all.
  * the new text detector classified a carrier by printable ratio. Zero-width
    characters are Unicode category Cf and report False for `isprintable()`,
    so a document carrying a zero-width payload measured 0.64 printable and
    was routed away as an unknown binary -- **the classifier rejected exactly
    the documents lab 20 exists to examine.** Classification is now by Unicode
    category, counting Cf and Mn as text.

**F-66 -- a documented tool behaviour that was never actually tested.**
`docs/TOOL_PRACTICE.md` claimed that `exiftool -all=` removes a payload from a
`tEXt` chunk, measured by searching the file for the payload string. The search
found nothing before the deletion and nothing after, because lab 03 encodes
what it embeds -- so the check "confirmed" a claim it had never tested.

Re-measured with the detector instead: E1 before, E0 after, the file 48 bytes
smaller. The claim was true; the evidence for it was not. Searching raw bytes
for a payload whose encoding you do not know proves nothing in either
direction, which is the same error as F-63's string search over an NTFS image.

The document's claims now ship as `tests/test_tool_practice.py`, because prose
recording tool behaviour goes stale the moment a distribution upgrades the
tool, and prose does not fail a build.

**F-65 -- "waiting for the paper" was a decision never tested by looking for
it.** G-11 stood open across the whole project. Three reconstructions from
memory failed, each recorded, and the correct conclusion was drawn -- do not
attempt a fourth. The conclusion that followed it was wrong: the paper was
treated as unavailable without a single attempt to find it. Dumitrescu, Wu and
Wang put the full text on the first author's university page, and one search
reached it.

Reading it located the error in one paragraph. The failed reconstructions
defined the trace sets X and Y by LSB PATTERN. The paper defines them by which
component of the pair is LARGER: among pairs differing by an odd amount,
X holds those whose even component is bigger and Y those whose odd component
is. Split by parity, X and Y are identically equal and every equation in the
model carries no p -- which is exactly the dead end recorded in F-38, correctly
diagnosed as a dead end and wrongly diagnosed as needing a missing assumption
about smoothness. The missing thing was a definition, not an assumption.

Implemented from equation (18), the estimator works first time: 0.05 -> 0.048,
0.20 -> 0.208, 0.40 -> 0.391 on synthetic covers, mean error +0.008 to +0.020
on real photographs against the 0.023 the paper reports on its own set. It is
flat on LSB matching, the required failure.

The habit worth keeping is narrow and specific: **"I cannot reconstruct this
from memory" and "this source is unavailable" are different claims, and only
the first was ever tested.** Refusing a fourth reconstruction was right;
letting that refusal stand in for a search was not.

**F-62 -- the NTFS ADS write worked all along; the read was wrong.** The
previous attempt was recorded as "the ADS write did not verify", which was a
fair description of what was seen and the wrong diagnosis. `ntfscp -N secret`
reported a new file size of 14 and completed; `ntfscat -a secret` then failed,
because `-a` selects an attribute TYPE and a stream name needs `-n`. One
letter, and it cost a session and nearly cost the gap.

Worth generalising: when a write reports success and a read fails, suspect the
read. The write path had told the truth in its own verbose output and I read
the failure as evidence about the write.

**F-63 -- a payload that reads back byte-exact and is not contiguous in the
image.** NTFS replaces the last two bytes of every 512-byte sector inside an
MFT record with an update-sequence number, keeping the originals in an array
at the top of the record. A resident stream spanning a sector boundary is
therefore broken in the raw image and perfect through a driver: a 480-byte
stream matched for 414 bytes and then stopped.

The first reading of that was also wrong -- the test payload was a 12-byte
repeating string, so `find` matched a shifted copy and the split looked like an
artefact of the search. A non-repeating payload showed the same break, which is
when the fixup explanation became testable. Same shape as F-44: the payload's
own structure changed what the measurement appeared to say.

The consequence for an examiner is worth stating plainly: **a raw string search
over a disk image can miss a payload that is plainly there.**

**F-64 -- NTFS metafiles use named streams, so the naive detector has a 100%
false-positive rate.** `$Bad`, `$SDS`, `$Info` and others are named $DATA
attributes on a freshly formatted volume. Reporting every named stream would
fire on every NTFS volume in existence. The detector excludes the known system
names and measures 0 findings on a clean volume -- the same shape as lab 20,
where zero-width characters do real linguistic work and lab 23's own deleted
file residue, where the innocent explanation is normal rather than rare.

**F-60 -- a gap can sit open for want of nobody going back to it.** G-12 was
recorded as "needs BOSSbase to separate corpus from implementation". BOSSbase
arrived several sessions later and G-12 was never revisited, because the gap
table is read for what to do next and a resolved prerequisite does not
announce itself.

Run now, it answers cleanly. Calibrated HCF-COM against LSB matching, AUC at
0.25 / 0.5 / 1.0 bpp: synthetic 0.531 / 0.540 / 0.510, real photographs
0.543 / 0.565 / 0.705. Both candidate causes recorded in the docstring were
testable and the second one holds -- calibration by down-sampling assumes
natural-image statistics and the synthetic corpus has none, the same
limitation as F-17. Ker's two-dimensional adjacency form adds a further
increment (0.735 at 1.0 bpp) but is not the main effect.

Worth adding to the maintenance habit: a gap whose blocker is an external
dependency should be re-run when that dependency lands, and nothing in this
repository prompts that. `scripts/analyst-checks.py` now would be the place.

**F-61 -- a gap row kept a falsified diagnosis in its description.** G-22's
fix column said CLOSED by keying the embedding path, while its description
column still asserted that coding loss is driven by the cost dynamic range --
the hypothesis that closing it disproved. A reader taking the description at
face value would carry away the wrong mechanism. This is the prefix-replacement
failure recorded earlier arriving in a new form: the row was updated where the
change was being made and not where the change made an older sentence false.

**F-59 -- "needs a real volume" was never true; it needed reading the tools'
manuals.** G-1 sat open for the whole project on the assumption that ext4 and
NTFS work required mount privileges. They do not. `mkfs.ext4` builds a volume
in a file, `debugfs -w -R write` populates it without mounting anything, and
`mkntfs`/`ntfscp` do the same for NTFS. The blocker was a belief about the
tools, not a property of the environment, and it survived several sessions
because nothing ever tested it.

With that gone, ext4 slack took one module: superblock geometry, the group
descriptor table, one inode and a depth-0 extent tree. Cross-checked against
debugfs on sizes, extent lists and the derived slack offsets. Deeper extent
trees, inline data and the ext2 indirect layout are refused explicitly rather
than guessed, because a slack offset computed from a misread extent points at
somebody else's data.

NTFS is the honest remainder: the image builds, but the alternate-data-stream
write did not verify in one attempt, and an unverified channel does not ship.

**F-58 -- the ordering fix paid twice, and the second payment was the
surprise.** Correcting convolution -> normalisation -> ABS to Xu-Net's
convolution -> ABS -> normalisation was made to explain why ABS lost to ReLU.
It did: the effect changed sign, ABS 0.1633 against ReLU 0.1700 where the
broken ordering had ReLU ahead by 0.0966.

But the whole network improved as well -- P_E 0.2333 to 0.1633 on BOSSbase at
128px, and the cost of removing the fixed high-pass layer grew from 0.26 to
0.33. Every figure T6 reported was depressed by a misplaced layer, including
the ones the chapter drew conclusions from. The bug was found by chasing a
result that contradicted the literature; it was costing accuracy everywhere,
silently, in measurements that all looked plausible.

Worth keeping: **a result that disagrees with published work is worth more as
a lead than as a finding.** Publishing 'ABS does not help' would have been
wrong and would have buried a real bug.

**F-56 -- a result that looked like evidence against the literature was
evidence about where I put a layer.** The 128px run measured ReLU 0.097 better
than ABS, four times the 64px gap, and a difference that GROWS with scale is
normally the end of a 'want of statistical power' defence. It was not: this
implementation had convolution -> normalisation -> ABS, while Xu-Net specifies
convolution -> ABS -> normalisation. Batch normalisation centres its output at
zero, so |x| of it is a half-normal with mean about +0.8 and nothing re-centres
it before the next convolution.

The gradient check settles it independently: the old ordering gives 5e-02
relative error, the corrected one 5e-09, because |x| has a kink at zero and a
normalised activation concentrates exactly there. The old ordering was not
merely suboptimal, it was not cleanly differentiable where it mattered.

So G-21 reopens rather than closing against the literature. What made the
difference was having a mechanism to test -- 'ABS does not help' is not
falsifiable, 'ABS after normalisation destroys the centring' is.

**F-57 -- and the same structural zero appeared one layer up.** With the
ordering corrected, `bn1.beta` only shifts its output, and the next
normalisation subtracts the mean, so its gradient is exactly zero everywhere.
A relative-error metric on a wholly zero tensor is undefined, and a floor
scaled to that tensor's own RMS is itself zero -- the fix for F-30 reappearing
one layer higher. The check now carries two floors: a tensor-relative one for
gradients that are rounding errors next to their own tensor, and an absolute
one for tensors that are entirely zero.

**F-54 -- a verifier that greps for one implementation's wording is worse
than no verifier.** `verify-toolchain.sh` probed djpeg by grepping its verbose
output for "Start Of Frame". That is IJG djpeg's wording; Kali ships
libjpeg-turbo, which decodes correctly and says something else. The result was
`[fail] djpeg` on a machine where djpeg works perfectly -- a false alarm, and a
false alarm in a verifier is as damaging as a missed one because it teaches
people to ignore the output.

The probe now decodes a real JPEG and checks the result, then separately checks
whether the gate can parse the verbose output, and reports those as different
facts.

**F-55 -- and my own new script had the opposite weakness.**
`check-crossval.py`, written the same session to expose silently skipped
cross-checks, established coverage with `shutil.which`. Being on PATH is not
the same as working: on that same Kali box it would have reported RUNS for the
djpeg whose output the gate cannot read. Every probe now executes the tool on a
generated carrier and checks the result -- pngcheck must list IHDR, djpeg must
report quantisation tables, ffmpeg must return exactly the right number of
pixel bytes, mkfs.vfat must produce a volume of the right size. The script
reports "not installed" and "present but unusable" separately, because only the
first is fixed by installing something.

Gate G1 makes the same distinction now: djpeg absent is one skip message,
djpeg present with unparseable output is another, and the second says plainly
that the cross-check is not running.

**F-52 -- a skipped cross-validation reports the same green as a passing one.**
Running on a real Kali box showed pngcheck, ffmpeg and mcopy absent. Every
test that compares a hand-written parser against an independent implementation
is guarded by `pytest.mark.skipif`, which is correct -- the suite has to run on
a machine without the tools -- but the consequence is that the suite reports
green while never checking the AVI parser against ffmpeg or the FAT parser
against mtools. Those comparisons are the single most valuable thing those
tests do.

Worse, `dosfstools` and `mtools` were never in `setup-kali.sh` at all: lab 23
was added this session and its dependencies were not. A machine following the
documented setup would have skipped the filesystem cross-checks permanently
and been told everything passed. Both packages are now in the installer, and
`scripts/check-crossval.py` prints RUNS or SKIP for every cross-validation so
the difference is visible before the suite is trusted.

**F-53 -- G-11's applicability settled, in the direction the synthetic corpus
could not show.** `spa_asymmetry` on 24 BOSSbase photographs gives an m=0 odd
fraction of 0.3811 (range 0.2222-0.5067) against 0.483-0.503 on synthetic
covers. Every trace-set equation degenerates to an identity at 0.5, so the
synthetic result said only that the corpus had nothing to estimate from. Real
photographs do: their smooth regions make h(0) much larger than h(1), and the
asymmetry the method needs is there. The estimator remains unbuilt, and
deliberately -- three reconstructions from memory have failed, and a fourth
would be the same mistake. What changed is that the question is now which
relation is missing, not whether the method applies at all.

**F-50 -- the first carrier where an innocent explanation is not rare but
normal, and no statistic separates it.** Lab 23 detects non-zero file slack.
A deliberate payload produces it. So does deleting a file and letting a smaller
one take its cluster -- the old file's tail survives in the new file's slack,
which is routine on any volume that has been used.

Constructed and measured: BIG.DAT of 'CONFIDENTIAL MEMO ' repeated 220 times,
deleted, then a six-byte NEW.TXT written into the same cluster. The detector
reports 3,954 non-zero slack bytes at 3.5 bits/byte and the extraction returns
'ENTIAL MEMO CONFIDENTIAL MEMO CONFIDENTI'. A deliberate payload of the same
length is indistinguishable: entropy does not separate them because either can
be text or compressed, and position does not because both start at the top of
the slack.

The detector therefore states BOTH readings in its claim text and hands the
recovered bytes to the analyst, rather than inventing a discriminator. Worth
noting which way the value runs: recovering the tail of a deleted confidential
memo is usually better evidence than proving somebody used steganography.

**F-51 -- the carrier is the volume, not the file.** Every earlier lab hid
inside a file, so copying the file carried the payload. Slack belongs to the
volume: copy the file out and the payload stays behind; defragment and it moves
or vanishes. An examiner who collected files rather than imaging the volume has
destroyed the channel before anyone looked at it. Ask what the carrier IS
before asking what is in it.

**F-49 -- two decoders agreeing proves nothing when they share a convention.**
The rewrite that added progressive support routed single-component BASELINE
files down the progressive non-interleaved path, which decodes DC and never
consumes the AC bits. The result was a smooth increasing DC ramp -- exactly
what a photograph's DC should look like -- and every AC coefficient zero. It
survived the encoder round-trip, because encode and decode shared the wrong
convention and reproduced the file byte for byte, and it survived the pixel
comparison for the same reason.

What caught it was computing the DC straight from the decoded pixels:
`dct(block)[0,0] / q[0]` gave [60.0, 23.96, 17.04, 2.88] where the decoder
claimed [60, 73, 100, 105]. The progressive path was right and the baseline
path was wrong, which is the opposite of the assumption the debugging had
started from.

The lesson is about the shape of the check, not the bug: an identity between
two implementations is only evidence if they cannot fail together. The
baseline-equals-progressive test is a good check precisely because the two
paths share no code below the scan loop -- but it needed a third, external
reference to establish which of them to trust. Both tests now ship.

**F-46 -- a global statistic is swamped by the untouched majority, for the
third time.** Lab 22's first temporal detector averaged the LSB flip rate over
the whole clip and measured 0.0076 on a carrier it should have found instantly.
A payload occupies a prefix of the embedding order, so it lands in the first
frames and every later pair is untouched; averaging over twenty-three pairs
divides the signal by twenty-three. Per pair, the same payload gives 0.083.

Lab 13 needed the same fix (windowed chi-square along Jsteg's writing order)
and so did lab 10 (windowed palette test). Three independent arrivals at one
rule: **whenever a payload is smaller than its carrier, measure along the
embedding order, not across the whole object.**

**F-47 -- sensor noise defeats the video temporal check, and the detector
declines rather than guessing.** A clip with mild sensor noise has a
static-region flip rate of 0.487 before anything is embedded -- the low bit is
already random. Four of twelve corpus clips are noisy and all four decline at
E1. This is the same shape as lab 18's bit-depth result and lab 21's IP-ID
cap: the honest move when a check has no power is to say so, not to produce a
number. Declining to run is a result.

**F-48 -- lossy re-encoding destroys the payload and the signal together.**
MPEG-4 at quality 3 takes the static-region median flip rate from 0.0000 to
0.0858, which trips the applicability floor, and the payload does not survive.
The video temporal check works on lossless video and nothing else. By gate G0's
taxonomy any transcoding pipeline is an active warden whether or not anyone
intended it, so "no steganography found" in an H.264 file says much less than
it appears to.

**F-43 -- three fixture bugs in one lab, each of which made a detector look
wrong.** Lab 21's embedders originally produced standalone captures rather than
injecting into background traffic. Consequences, in order of discovery:

  * the IP-ID channel was reported by the TIMING detector, because a capture
    containing nothing but the embedder's packets has the embedder's fixed gap
    as its only inter-arrival time. The detector was right about what it saw;
    what it saw was the fixture.
  * the timing embedder gave its unused tail a third fixed gap, which diluted
    the top-two-value share below the threshold and hid the channel. The
    embedder was making traffic look MORE natural than a real channel would,
    so the measurement flattered it. Real channels retime only what they use.
  * the IP-ID detector required EVERY DF packet to carry a non-zero ID. No
    channel does that -- an embedder writes into the packets it needs and
    leaves the rest alone, so the anomaly is a mixed population. Requiring it
    of the whole capture made the detector silent on the case it was written
    for.

All three are the same error as F-24: a fixture built to exercise a code path
exercises the path, not the physics.

**F-44 -- the payload's own entropy changes whether the channel is
detectable.** DNS tunnel uniqueness ratio on a 2,000-byte payload: 1.00 for
random bytes, 0.01 for a repeated single character. The uniqueness detector
reports nothing on the second. An unsophisticated sender who does not compress
accidentally defeats a detector aimed at sophisticated ones, and every detector
built on "covert traffic looks random" inherits this. The answer is a signal
that does not depend on entropy -- volume and label length still fire -- which
is why the DNS test requires all three conditions rather than any one.

**F-45 -- the IP-ID channel ships capped at E1, on purpose.** A randomising
TCP/IP stack produces exactly the evidence a payload does. The finding says so
in its own claim text rather than leaving the analyst to notice. Separating the
two needs a baseline for what that HOST normally does -- the same-source
requirement arriving as a statement about a host rather than a camera.

**F-41 -- text is the first carrier whose hiding places have legitimate
owners, and it changes what a baseline means.** Every earlier lab hid in bytes
nothing legitimate needed: an unregistered chunk, a segment no decoder reads,
silence that is exactly zero. The characters used to hide in text do real
linguistic work -- ZWNJ separates Persian morphemes, ZWJ builds emoji sequences
and Devanagari conjuncts, VS16 makes an emoji render as one. A detector that
flags invisible characters reports every multilingual document ever written.

Three contextual signals separate carrying from writing, measured at 0/8 false
positives on a corpus that includes Persian ZWNJ, emoji ZWJ sequences,
Devanagari conjuncts, CJK ideographic variation sequences and a leading BOM:
run length, script context, and selector range.

The two zero-width signals are independent, and that turns out to matter. A
naive embedder writes 104 zero-width characters in one run, which run length
finds instantly. A careful one spreads single bits between letters: longest run
1, runs over threshold 0 -- and 48 runs sitting between two ASCII letters,
where no script places a joiner. The adversary who defeats one signal walks
into the other, which is the argument for having both rather than tuning one.

The consequence for the evidence ladder is worth stating: every other lab could
treat its false-positive baseline as a property of the SOURCE. Here it is a
property of the LANGUAGE. A detector calibrated on English prose and applied to
Persian is not slightly wrong; it is useless.

**F-42 -- trailing whitespace needed the same treatment and nearly shipped
without it.** `trailing_whitespace_lines` was computed and never wired into
`detect`, so the SNOW channel embedded, extracted, and was reported as E0.
Wiring it naively would have been worse: editors leave stray trailing spaces
and Markdown's hard-break convention is two trailing SPACES, so a line count
flags ordinary documents. Tabs (which prose never produces) plus contiguity (a
payload occupies a prefix of consecutive lines) give 22 tabs and a 32-line run
on the SNOW carrier against 0 tabs and a 1-line run on Markdown.

**F-39 -- bit depth defeats the statistical detector and does nothing to the
structural one.** Lab 18 runs the same Weighted Stego estimator on 8-bit and
16-bit audio at the same relative payload. Clean against stego: 0.0130 to
0.2689 at 8 bits, a ratio of 20.7x; 1.1822 to 1.3253 at 16 bits, a ratio of
1.1x. The estimator is unchanged and the carrier's precision is the only
difference -- an LSB flip moves an 8-bit sample by 1/256 of full scale and a
16-bit sample by 1/65,536, forty-eight decibels quieter. This is arithmetic
rather than a tuning problem, and it generalises: anything that raises a
carrier's precision buys the embedder the same protection.

The silence check is untouched by it -- 0/16 false positives at both depths --
because it is asking a structural question, not a statistical one.

**F-40 -- two silent format traps in one lab.** 8-bit WAV is UNSIGNED with
midpoint 128; wider formats are signed with midpoint 0. Searching for zeros in
an 8-bit clip finds the waveform's most negative excursions and misses the
silence entirely. And the silence search has to look for samples *within one*
of the level rather than equal to it, because embedding is exactly what puts
the ones there -- an exact-match search makes an embedded passage invisible to
the check meant to catch it. Both would have produced a detector that ran
cleanly and found nothing.

A third, caught by measurement: flagging any silent run containing off-level
samples gave 2/16 false alarms at 8 bits, where the quantiser makes a quiet
musical passage indistinguishable from silence by amplitude. LSB replacement
can only produce the level or one ABOVE it, while a real quiet passage crosses
in both directions. Requiring one-sided deviations took false positives to 0/16
at both depths.

**F-38 -- G-11: the trace-set equations are identities, and the measurement
that decides whether SPA applies at all now ships.** The gap was recorded as
needing "one cover assumption relating the odd-difference count to the
even-difference count within a trace set". Measuring that relation directly
settles it, and not in the hoped-for direction: (X + Y) / Z is 1.00 within
0.03 across trace sets m = 1..5 and across five covers.

That is not a smoothness property of the difference histogram. It is
P(lu = lv) = 1/2 -- the cover's LSBs being unbiased and independent of the
coarse class -- and it holds in the stego too. Substituted into the sum
equation X' + Y' = (X + Y) + 2 p q (N - 2 (X + Y)) it zeroes the coefficient,
because N - 2(X + Y) = 0 when X + Y = N/2. Together with the difference
equations already shown to vanish, every relation in the parameterisation
becomes an identity carrying no q.

The asymmetry can only live at m = 0, where the LSB pattern is forced by the
difference: u = v requires lu = lv, |d| = 1 requires lu != lv. For a
photograph with smooth regions h(0) >> h(1), so (X + Y) / N should sit well
below 1/2. On this repository's synthetic covers it does not -- measured 0.483
to 0.503, with the coefficient the estimator would divide by at 19, -21 and 100
out of N = 3968. There is nothing to estimate from, which is the same corpus
limitation that cost the statistical detectors their low-payload sensitivity
(F-17).

So `spa_asymmetry` ships as the next step rather than another estimator. If
`m0_odd_fraction` on BOSSbase sits well below 0.5, SPA is applicable here and
the remaining work is one cover assumption. If it sits at 0.5 there too, the
method needs a different parameterisation than trace sets -- and knowing which
is worth more than a fourth reconstruction.

**F-37 -- G-22 closed: it was the traversal order, not the costs.** Five
sessions of sub-hypotheses -- poor submatrices, cost dynamic range, wet paper
codes, submatrix quality at other widths -- and the answer was that the trellis
visited cover elements in raster order.

The trellis has a lookahead of h. Costs are spatially clustered, because
texture is. On a cover whose left half is flat, a raster-order trellis spends
the first half of its run with no cheap element anywhere inside its window, so
the syndrome forces flips onto elements costing many times the median, and a
handful of those dominate the total distortion. Measured on the composite
cover at w=10, the costliest forced flip was 1.59 against a cost median of
0.085.

Keying the embedding path interleaves cheap and expensive elements, so a cheap
option is almost always within the window:

    cover        w    raster    keyed
    photo_like   2     11.6%     7.2%
    photo_like  20     38.7%    22.8%
    composite    2    283.7%    22.0%
    composite   10     71.3%    15.2%
    composite   20    146.1%    18.6%
    80% flat     2     76.1%    26.6%

Everything lands in a 7-27% band instead of spanning 12% to 284%, and the
costliest forced flip at w=10 falls from 1.59 to 0.083 -- from 19x the median
to the median. End to end through `embed_adaptive`, the composite cover at
0.4 bpp goes from 278.0% to 20.0%. Gate G3's criterion B, re-measured on the
keyed path, now reads 10.01% / 7.96% / 5.98% at h = 8 / 10 / 12 -- inside the
published 5-10% band -- so its bar tightened from 15% to 12%.

Every earlier sub-hypothesis is explained as a consequence. A submatrix cannot
fix an ordering problem, which is why searching them bought only feasibility
(F-31, F-34). Cost dynamic range was a proxy: the wide-range covers in this
corpus are the spatially clustered ones -- composite is literally half flat.
And wet paper codes failed because they delete the clustered capacity instead
of reordering access to it (F-33).

The permutation is part of the shared secret, like the submatrix. Every real
implementation keys the embedding path. This one did not, and five sessions
went into rediscovering why they do.

**F-35 -- the shrinkage signature was real all along; the reference was the
problem.** Gap G-20 recorded that excess zeros could not tell F5 from its
shrinkage-free variant, at AUC 0.622-0.736, and correctly diagnosed why: the
calibration reference is computed from the stego image, so any embedder that
alters pixels moves the reference too. Replacing it with a population model
built from clean same-source carriers -- which the evidence ladder already
requires for a baseline, so it costs nothing new -- gives AUC 1.000.

The z-scores against that model show the mechanism directly, over 15 held-out
carriers at 0.15 bpp:

    bin      clean      F5    variant
    d=0      -0.05   +2.42     -0.07
    d=1      +0.03   -2.60     -1.12
    d=2      +0.72   -1.94    +11.76

F5 decrements magnitude-1 coefficients into zero and the zero bin gains. The
variant increments them to two instead, so the zero bin does not move at all
and the |2| bin gains sharply. Both predictions confirmed, and neither was
visible through a reference that moved with the carrier.

**F-36 -- the validation fixture's own LSBs were biased.** `spa_synthetic_pairs`
first built covers as (even base + offset), which left (Z00 - Z11)/N at +0.078
where a natural cover gives about zero. An estimator that correctly assumes
unbiased cover LSBs would have failed on the fixture for a reason having
nothing to do with the estimator -- the third time in this project that a test
artefact would have been read as a result. Replaced with a correlated random
walk: +0.0002 and -0.003.

**F-33 -- wet paper codes do not fix G-22, and the reason is structural.**
The recorded next step for G-22 was wet paper codes: cap costs AND exclude the
capped elements from the embedding path, so no syndrome can force an expensive
flip. Implemented (`wet_mask`, a `wet=` parameter on `stc_embed`, a bound that
excludes wet elements, and a named CapacityError). It does not help.

Measured at h=10 with the wet set taken from the Gibbs optimum at pi < 1e-3:
where exclusion was feasible the gap to the bound moved by 0%, and once by
-9%; where it would have mattered -- a wide-cost cover at 0.05, 0.1 and
0.4 bpp -- the payload became infeasible instead of cheap. On that cover 39% to
51% of elements sit below the probability floor, so excluding them leaves less
dry capacity than the payload needs.

The reason is that a wet paper code converts "expensive" into "impossible".
Where the Viterbi search had a cheap alternative it was already taking it, so
exclusion adds nothing; where it had none, exclusion removes the embedding
rather than improving it. `wet_paper` therefore ships opt-in rather than on by
default -- it is an honest model of a genuinely wet channel, not a coding
improvement.

**F-34 -- and it is not submatrix quality at other widths either.** The
submatrix table only covers w=2, so every other payload falls back to a random
draw, which was the obvious next suspect. Measured over 12 draws at w in
{2, 5, 10, 20} on two covers: the spread between best and worst draw is 1.09x
to 1.66x at every width. Same conclusion as F-31, now at every w.

What the same sweep does show is a shape. On a narrow-cost cover the gap grows
monotonically as the payload shrinks -- 12.7%, 21.6%, 29.6%, 38.6% at w = 2, 5,
10, 20 -- because the bound shrinks faster than the trellis can track it. On a
wide-cost cover it is worst at both extremes: 276% at w=2 (one bit per covered
element, saturation) and 146% at w=20, with a minimum of 41% at w=5. So the
quantity to quote is not "STC's coding loss" but "STC's coding loss at this
payload, this width, and this cost distribution" -- the same lesson this
repository keeps arriving at about thresholds.

**F-32 -- criterion B minimised over cover identity as well as over
submatrix.** `sweep_h` collected one gap per (cover, seed) pair and took the
minimum of the flattened list, so the figure reported as "best submatrix" was
partly reporting the easiest cover in the set. It now takes the minimum over
seeds within each cover and averages those, which is the quantity the criterion
is about -- a good submatrix on a typical cover. The corrected mean-over-best
ratio is a flat 1.2x at every constraint height, consistent with F-31.

**F-30 -- a convolution followed by batch normalisation has an exactly zero
bias gradient, and a relative-error metric on two zeros returns garbage.**
Gate G6's gradient check passed on synthetic covers and then failed on real
ones, reporting a relative error of exactly 1.00 for conv1.b while every other
parameter sat at 1e-8. Nothing was broken: BN subtracts the batch mean per
channel, so adding a constant to the preceding convolution's output changes
nothing, the true gradient is zero, both sides of the comparison were
floating-point noise, and `|a-b| / (|a|+|b|)` on two zeros is meaningless. It
passed on synthetic only because the five sampled indices happened to land
well -- a flaky check, which is worse than a failing one.

Fixed twice over: the redundant biases are gone (56 dead parameters, and it is
why frameworks default to `bias=False` before BN), and the metric now has an
absolute floor below which two gradients are simply both zero. The check also
now covers the BN parameters, which it never did.

**F-28 -- the pipeline committed the error the course exists to warn about.**
Gate G7 failed its no-over-claims criterion on the first run: three of seven
clean carriers reported at E3, all in the jpeg-dct domain. Every statistical
detector was running on every carrier, so lab 14's operating point -- measured
on grayscale JPEGs at quality 90 -- was applied to colour JPEGs, and lab 07's,
measured on grayscale PNGs, to anything. T4 and T5 both measure what that
mistake costs; the pipeline was making it. Container-type dispatch, plus a
refusal to apply a grayscale-calibrated threshold to a colour carrier (decided
by parsing IHDR colour type or SOF component count, not a filename), took
over-claims from three to zero and accuracy from 0.90 to 1.00.

**F-29 -- a claim withdrawn after measurement.** Lab 14 originally used excess
zeros to name F5 against nsF5. Measured discrimination given only stego images:
AUC 0.622 at 0.05 bpp, 0.736 at 0.15. The cause is structural -- the
calibration reference is computed from the stego image, so any embedder that
alters pixels shifts the reference and the shrinkage signal does not survive
the subtraction. The finding now names the family, not the member. What does
separate them is beta, at AUC 0.811 and 0.984, because shrinkage makes F5
change twice as many coefficients for the same payload (0.099 against 0.044) --
which is a better argument for nsF5 than the histogram story it replaces.

**F-26 -- an instrument that reads zero on the phenomenon it was built for.**
`wet_fraction` was added to explain enormous distortion bounds by reporting
the share of unusable elements. On real BOSSbase covers it read 0.000 -- on
exactly the covers whose expensive elements had crashed the lambda search one
run earlier. The threshold was WET_COST itself, the exact clamp value, reached
only where the filtered residual is precisely zero; real costs approach the
ceiling without touching it. It now measures an order of magnitude below, and
reports cost quantiles alongside, because max/min alone cannot distinguish a
cover that is mostly unusable from one with a narrow bulk and a thin tail.

**F-27 -- averaging over random draws answered the wrong question.** Criterion
B reported the mean gap over four random submatrices, which measures how bad
an arbitrary matrix is. A submatrix is chosen once at design time and is part
of the shared secret. On real covers mean and best differ by 3.5x (38.72%
against 11.12% at h=12), so the statistic being graded was almost entirely
about the draw. B now grades the best and reports the spread as G-16's
evidence.

**F-25 -- a test using os.urandom is not a test.** Lab 13's length-estimate
test drew payloads from os.urandom, so the payload differed every run. At the
smallest payload the windowed chi-square sits near its detection boundary, and
the suite therefore passed or failed by luck -- it passed for two sessions and
then failed. Payloads are now seeded, and the test was rerun three times to
confirm it lands the same way. A test that cannot be rerun to the same answer
cannot be debugged.

**F-24 -- the stand-in lacked the one property that broke the real thing.**
G3's real-corpus path was validated against a synthetic stand-in with noise
everywhere. Real photographs have genuinely FLAT regions -- sky, walls, blown
highlights -- where HILL's residual goes to zero and the cost hits its 1e10
ceiling. On a BOSSbase frame that is 92% wet, the lambda search's hardcoded
lower bracket of 1e-8 already gives lambda * rho = 100 and pi = 0 for every
wet element, so the entropy at the lower endpoint was below the requested
payload, both endpoints had the same sign, and scipy raised mid-gate. The
RuntimeWarnings about exp overflow were the visible half of the same bug.

Fixed three ways: the bracket expands in both directions, pi is computed with
expit so large arguments saturate rather than overflow, WET_COST is named
explicitly, and `wet_fraction()` is reported by G3 -- a cover that is 90% wet
is carrying its payload in the remaining 10%, and nothing in a distortion
figure hints at that otherwise. Over-capacity now raises CapacityError with
the numbers in it instead of surfacing as a root-finder complaint.

The lesson is about the stand-in, not the solver: a fixture built to exercise
a code path will exercise the path and not the physics. Gaussian noise has no
flat regions, so it could never have found this.

**F-20 -- a fixed w silently changed the experiment, and the control caught
it.** `embed_adaptive` hardcoded w=2, so at 0.05 bpp the trellis covered
2 * 0.05n = 10% of the image taken as a raster PREFIX -- embedding only ever
touched the top tenth. The placement statistic then described what happened
to be in the top tenth: with UNIFORM costs, where placement must be
content-blind, the textured-to-smooth ratio read 0.55 instead of 1.0. With w
derived from the payload the control reads 0.99 and HILL reads 5.69 at 0.05
bpp. A control that fails is how you learn the experiment is confounded, and
it is the reason to run one even when the answer seems obvious.

**F-21 -- adaptivity's benefit is a function of the payload, and one rate
hides it.** HILL's textured-to-smooth concentration on real covers: 5.48x at
0.05 bpp, 2.17x at 0.1, 1.46x at 0.2, 1.14x at 0.4. Cheap regions saturate,
and the coder must spill into expensive ones. G3 ran every criterion at 0.4
bpp, which made adaptivity look nearly useless; it now uses 0.4 for the
coding-efficiency criteria and 0.1 for the adaptivity criteria, each labelled.

**F-22 -- "no difference" between two undetectable things is not a result.**
At 0.1 bpp with 48 covers, SPAM686 detects neither HILL+STC nor LSB matching
(P_E 0.4375 both). Grading a security-gain criterion there would have been
measuring noise. Criterion E now checks that the BASELINE is detectable
before comparing anything to it -- the same precondition gate G0 applies when
it verifies its control extraction succeeds before reporting that the warden
broke it.

**F-16 -- a threshold picked by quantile breaks on tied scores.** The
false-positive baseline used `quantile(stego, 1 - target)`. On real covers
most chi-square p-values are exactly 0.0, so the threshold came out at 0.0,
every clean cover satisfied `>= 0.0`, and gate G4 reported "FPR = 1.000 at
threshold 0.0" as a measurement. It now scans candidate thresholds for the
minimum achievable FPR and states explicitly when a detector has no operating
point -- a result about the detector, not a rate.

**F-17 -- the synthetic corpus was costing the detectors their low-payload
sensitivity.** At 0.05 bpp, Weighted Stego's AUC against LSB replacement is
0.594 on synthetic covers and 0.882 on BOSSbase. Chi-square's clean-cover
mean p-value goes from 0.944 to 0.129, turning an unusable detector into a
working one. The claim that synthetic covers were inadequate had been argued
from first principles since P1; this is the measurement.

**F-18 -- "cover source mismatch" is two different effects with an order of
magnitude between them.** Cross-camera within BOSSbase: P_E 0.125 to 0.160.
One resample of the same images from the same camera: 0.163 to 0.500. Every
BOSSbase image went through the same development script, so cross-camera
isolates the sensor. G5 criterion D failed on real data because it demanded
the severe magnitude from the mild shift; it was split into D1 (sensor) and
D2 (pipeline) rather than having its threshold lowered.

**F-19 -- a similarity criterion can fail for the wrong reason.** G5's
criterion C required the two embedders' P_E values to agree within 0.10 and
measured 0.095 on real data. It would have failed if SPAM had got *better* at
replacement. The claim is that neither embedder is invisible, so the criterion
now requires both below 0.25.

**F-23 -- registration has to be authoritative.** The gates re-discovered the
corpus themselves by matching a filename containing "boss", so a corpus
registered under any other name was invisible: registration reported USABLE
and the gates then said no corpus was registered. They now read the index that
registration writes.

**F-15 -- a corpus that loads is not a corpus that means anything.** The
reference loader was validated against a stand-in built from Gaussian noise.
It loaded cleanly, passed verification, and ran end to end through gates G4
and G5 producing full tables of AUC figures -- all meaningless, because
white noise has no spatial correlation and every detector here assumes
plenty. `verify()` now measures lag-1 horizontal correlation and refuses a
corpus below 0.80; the stand-in measures 0.0004.

**F-12 -- Jsteg skips magnitude, not value.** The P1 embedder excluded
coefficients equal to 0 and 1, letting -1 through. Writing a 0 bit into -1
produces 0, removing that coefficient from the extraction path and
desynchronising every bit after it. Extraction failed at byte 1. G2's
criterion D had passed with a 4.75% skip-pair drift against a 5% tolerance,
which in hindsight was this bug creeping in under the bar.

**F-13 -- the chi-square negative pairs mirror, they do not shift.**
Magnitude 2 pairs with 3, so -2 pairs with -3. Pairing -2 with -1 puts an
untouchable value into the test: -1 keeps its natural count while -2 is
flattened against nothing. The statistic returned 0.000 on every window
including fully embedded ones, so the detector looked dead rather than
wrong.

**F-14 -- the textbook threshold was wrong for this carrier.** "p near 1"
would have missed every Jsteg payload under about 1200 bytes. Measured on 30
clean covers, the maximum window p-value was 0.277 and embedded windows sat
between 0.5 and 0.99, so the operating point is 0.40. Another instance of
the rule that thresholds are properties of a carrier, not of an algorithm.

**F-9 -- cover source mismatch is not degradation, it is collapse.** T4 saw
a false-positive rate move 0% to 25%. G5 measured the classifier version:
training on texture/photo_like and testing on gradient/flat moves P_E from
0.140 to 0.487, which is chance. The classifier does not transfer badly; it
stops working. This is why lab 09's `detect` refuses to run without a
classifier argument rather than shipping a pre-trained one.

**F-10 -- a single-image assertion tests luck.** Lab 09's first detection
test embedded one payload and asserted the classifier caught it. It failed,
correctly: a classifier with P_E near 0.3 misses individual images by
construction. Everything from lab 07 onward is a statistical verdict and has
to be asserted statistically -- the test now measures a detection rate
against a false-alarm rate.

**F-11 -- SPA resisted a second reconstruction, and the attempt is recorded
rather than repeated.** P2 derived the exact trace-set transition equations
(each LSB flips independently with probability q, so E[X'] = X(1-q)^2 + Yq^2
+ Zq(1-q) and its symmetric partner, with |X_m|+|Y_m|+|Z_m| invariant per
coarse class) and identified that the missing piece is the cover assumption
relating the sub-multisets across adjacent trace sets, not the transition
model. That is real progress and it is where P3 starts. No third
reconstruction was attempted, because two failed attempts are evidence that
the source paper is required rather than optional. G-11 stays open.

**F-6 -- shrinkage costs F5 more than a histogram notch.** G2's efficiency
and rate criteria originally ran against plain F5 and failed by a consistent
~45%. Not a defect: a shrinkage event spends a change and carries no bits,
so plain F5 *cannot* meet the textbook figures. Measured at k=3, shrinkage
costs 45.3% of efficiency, taking plain F5 to 1.87 -- below plain LSB's 2.0,
which matrix encoding exists to beat. The criteria were moved to the code
where the arithmetic applies, following the precedent that a falsified
criterion gets restated rather than the target made easier.

**F-7 -- cover source mismatch, found by accident.** Lab 07's
zero-false-positive test failed on first run at 25%. The detector was fine;
the baseline mixed four image families including flat and gradient covers,
where RS and WS become unstable. Same detector, same threshold, matched
baseline: 0/60. Mixed baseline: 15/60. This is the effect T5 treats as a
central problem, and it turned up as a test failure.

**F-8 -- the noise hypothesis for HCF-COM is falsified.** The obvious
explanation for calibrated HCF-COM being at chance was that these covers
carry more high-frequency noise than a +/-1 perturbation. Sweeping cover
noise from sigma=0.5 to sigma=6.0 left AUC within [0.505, 0.533] while cover
local standard deviation moved only 5.66 to 7.53, because the upsampled base
dominates it. Recorded because a plausible explanation that survives
unchallenged is worse than no explanation.

**F-5 -- the 4.0x figure.** The Rust triage scanner is only four times
faster than Python, not the order of magnitude one might assume. Container
triage is dominated by I/O and slicing, both already C inside CPython. The
Rust sideline's justification has to come from the statistical layer, where
per-pixel work runs in Python loops. Recorded so the sideline is judged on
evidence rather than on the assumption that Rust is fast.

## Inherited gap, closed on day one

**N-4 (from sc-audit-lab)** -- documentation commands were never validated,
which let a non-existent flag survive across six documents and two merges,
and shell-unsafe angle-bracket placeholders recur three further times.
`scripts/check-docs.py` now includes a `commands` checker that verifies flag
existence against `--help`, rejects `<PLACEHOLDER>` forms, checks Makefile
targets exist and confirms referenced scripts are present.

---

[Chinese version](GAP_ANALYSIS_zh.md)
