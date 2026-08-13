#!/usr/bin/env bash
# Where to get the reference corpora, and where to put them.
#
# Nothing is downloaded here. These archives are large, some carry terms that
# are not ours to accept on your behalf, and none of them belong in a git
# repository. The synthetic corpus in corpus/generate.py stays sufficient for
# the structural labs and is demonstrably insufficient from gate G4 onward.

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ROOT}/corpus/reference"
mkdir -p "$DEST"

cat <<'NOTE'
Reference corpora for the statistical chapters (T4, T5, and T3's security claim).

  BOSSbase 1.01 -- 10,000 grayscale 512x512 PGM from seven cameras.
    The original host is unreliable: agents.fel.cvut.cz frequently refuses
    connections, and the old boss/index.php entry point is gone entirely.
    Use the Binghamton mirror:

      http://dde.binghamton.edu/download/ImageDB/BOSSbase_1.01.zip

    1.6 GB compressed, about 2.6 GB unpacked. LEAVE IT ZIPPED if disk is
    tight -- the loader reads zip members directly.

    If you want the original host anyway:
      http://webdav.agents.fel.cvut.cz/data/projects/stegodata/BossBase-1.01-cover.tar.bz2

  BOWS2 -- 10,000 grayscale 512x512.
    bows2.ec-lille.fr is DEAD. No maintained mirror is known. A second
    camera source is needed for cover-source mismatch work; BOSSbase's own
    seven-camera split covers that case, so BOWS2 is no longer on the
    critical path.

  ALASKA2 -- ~75,000 colour JPEG at several quality factors, with
    J-UNIWARD, UERD and nsF5 stego versions. Needs a Kaggle account:
      https://www.kaggle.com/c/alaska2-image-steganalysis/data

Install:

    mkdir -p corpus/reference
    mv ~/Downloads/BOSSbase_1.01.zip corpus/reference/
    python3 scripts/register-corpus.py

Then the gates can use it:

    python3 gates/g4_statistical.py --corpus real --n 200
    python3 gates/g5_feature_sets.py --corpus real --n 400 --train-camera canon_eos_7d --test-camera nikon_d70

Licensing: each corpus carries its own terms. Read them before using results
in anything published or evidential. Nothing is redistributed here.
NOTE

echo
echo "corpus/reference/ currently contains:"
ls -1 "$DEST" 2>/dev/null | sed 's/^/  /' || true
[ -z "$(ls -A "$DEST" 2>/dev/null)" ] && echo "  (empty)"
