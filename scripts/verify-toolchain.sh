#!/usr/bin/env bash
# Verify the toolchain is USABLE, not merely present.
#
# `command -v` proves a binary is on PATH. It does not prove the binary runs,
# that its shared libraries resolve, or that it does what the guide assumes.
# Every check here therefore executes a real operation on real input.

set -uo pipefail

PASS=0
FAIL=0
SKIP=0

ok()   { printf '  \033[32m[ ok ]\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m[fail]\033[0m %s -- %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }
skip() { printf '  \033[33m[skip]\033[0m %s -- %s\n' "$1" "$2"; SKIP=$((SKIP+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== python =="
if python3 -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
  ok "python3 >= 3.10"
else
  bad "python3" "need 3.10 or newer"
fi

for mod in numpy scipy PIL sklearn cv2 matplotlib pytest; do
  if python3 -c "import $mod" 2>/dev/null; then
    ok "python module $mod"
  else
    bad "python module $mod" "import failed"
  fi
done

echo "== reference tools (gates depend on these) =="
python3 - "$TMP" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, ".")
from pathlib import Path
from steganalysis import corpus
out = Path(sys.argv[1])
(out / "t.png").write_bytes(corpus.render(corpus.CoverSpec("t.png", 1, 64, 48, "texture", "png")))
(out / "t.jpg").write_bytes(corpus.render(corpus.CoverSpec("t.jpg", 2, 64, 48, "photo_like", "jpeg")))
PY

if [ -f "$TMP/t.png" ]; then
  if command -v pngcheck >/dev/null && pngcheck -v "$TMP/t.png" 2>/dev/null | grep -q "chunk IHDR"; then
    ok "pngcheck lists chunks"
  else
    bad "pngcheck" "not installed or produced no chunk list (gate G1 will skip)"
  fi
  # Probe what djpeg DOES, not what it says. IJG's djpeg and libjpeg-turbo's
  # print different verbose text -- grepping for one implementation's wording
  # reported a working djpeg as broken on Kali, which is the worse kind of
  # false alarm: it teaches people to ignore the verifier.
  if command -v djpeg >/dev/null && djpeg -pnm -outfile "$TMP/t.pgm" "$TMP/t.jpg" 2>/dev/null \
     && head -c2 "$TMP/t.pgm" | grep -q "P"; then
    if djpeg -verbose -verbose -outfile /dev/null "$TMP/t.jpg" 2>&1 | grep -qiE "quantization table|start of frame"; then
      ok "djpeg decodes and reports tables"
    else
      bad "djpeg" "decodes, but gate G1 cannot read its verbose output -- the JPEG cross-check will SKIP silently"
    fi
  else
    bad "djpeg" "not installed or cannot decode (gate G1 will skip; apt install libjpeg-progs)"
  fi
else
  skip "pngcheck/djpeg" "could not generate test carriers"
fi

if command -v steghide >/dev/null; then
  echo "secret" > "$TMP/s.txt"
  if steghide embed -cf "$TMP/t.jpg" -ef "$TMP/s.txt" -sf "$TMP/st.jpg" -p pw -q -f 2>/dev/null \
     && steghide extract -sf "$TMP/st.jpg" -xf "$TMP/o.txt" -p pw -q -f 2>/dev/null \
     && diff -q "$TMP/s.txt" "$TMP/o.txt" >/dev/null; then
    ok "steghide round-trips a payload"
  else
    bad "steghide" "present but the embed/extract round trip failed"
  fi
else
  bad "steghide" "not installed (gate G0 criterion B2 will skip)"
fi

echo "== optional tools =="
for t in binwalk foremost exiftool zsteg stegseek bulk_extractor tshark sox ffmpeg; do
  if command -v "$t" >/dev/null; then ok "$t"; else skip "$t" "not installed"; fi
done

echo "== rust sideline =="
if command -v cargo >/dev/null; then
  if (cd rust/stegscan && cargo build --release --offline -q 2>/dev/null); then
    ok "stegscan builds offline"
  else
    bad "cargo" "present but stegscan failed to build"
  fi
else
  skip "cargo" "not installed (difftest will skip)"
fi

echo
printf 'verify-toolchain: %d ok, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]
