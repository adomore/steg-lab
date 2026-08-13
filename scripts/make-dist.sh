#!/usr/bin/env bash
# Build the release tarball.
#
# Excludes everything reproducible: generated corpora, gate results, build
# artefacts, reference corpora pulled by get-corpora.sh. A release that ships
# its own outputs invites the reader to trust them instead of regenerating.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(tr -d '[:space:]' < VERSION)"
NAME="steg-lab-v${VERSION}"
OUT="${1:-/tmp}"

tar czf "${OUT}/${NAME}.tar.gz" \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='corpus/generated' \
  --exclude='corpus/reference' \
  --exclude='gates/results' \
  --exclude='rust/stegscan/target' \
  --exclude='reference' \
  --exclude='*.tar.gz' \
  --transform "s,^\.,${NAME}," \
  .

echo "wrote ${OUT}/${NAME}.tar.gz"
tar tzf "${OUT}/${NAME}.tar.gz" | wc -l | xargs printf '%s entries\n'
