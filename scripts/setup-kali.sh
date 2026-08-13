#!/usr/bin/env bash
# steg-lab toolchain installer for Kali Linux.
#
# Three layers, installed in dependency order:
#   1. apt        -- system tools the gates and labs shell out to
#   2. python     -- the scientific stack the reference implementation uses
#   3. optional   -- large or source-built tools, behind flags
#
# On PEP 668 systems (Kali 2024.1 and later, Debian 12+, Ubuntu 23.04+) a
# bare `pip3 install --user` aborts with "externally-managed-environment".
# Under `set -e` that kills the whole script, which is how the smart-contract
# lab's installer died on Kali 2026.3. The degradation chain below --
# pipx, then --break-system-packages, then an explicit skip with instructions
# -- exists so that one unavailable installer never takes down the rest.
#
# Environment flags:
#   INSTALL_OPTIONAL=1   ruby/go/java tooling (zsteg, stegseek, StegExpose)
#   INSTALL_ML=1         PyTorch for the T6 deep-learning chapter
#   INSTALL_RUST=1       Rust toolchain for the stegscan sideline
#   ASSUME_YES=1         non-interactive apt

set -uo pipefail

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null; then SUDO="sudo"; else
    echo "!! not root and sudo is unavailable; apt steps will be skipped"
  fi
fi

APT_YES=""
[ "${ASSUME_YES:-0}" = "1" ] && APT_YES="-y"

note() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$1"; }

# ---------------------------------------------------------------- layer 1

note "layer 1: apt packages"
APT_PKGS=(
  # gates G0/G1 shell out to these -- they are not optional
  pngcheck libjpeg-progs steghide
  # container and metadata triage
  binwalk foremost bulk-extractor libimage-exiftool-perl
  # image, audio and capture handling
  imagemagick ffmpeg sox tshark
  # lab 23 builds and writes FAT volumes; without these its tests SKIP
  dosfstools mtools
  # archives, hex, general
  p7zip-full unzip zip vim-common file
  # build prerequisites for source-built tools
  build-essential pkg-config
  # python
  python3 python3-pip python3-venv
)

if [ -n "$SUDO" ] || [ "$(id -u)" -eq 0 ]; then
  $SUDO apt-get update $APT_YES || warn "apt-get update failed; continuing"
  for pkg in "${APT_PKGS[@]}"; do
    if $SUDO apt-get install $APT_YES -qq "$pkg" >/dev/null 2>&1; then
      printf '  installed %s\n' "$pkg"
    else
      warn "could not install $pkg (name may differ on your release)"
    fi
  done
else
  warn "skipping apt layer"
fi

# ---------------------------------------------------------------- layer 2

note "layer 2: python packages"

PY_PKGS=(numpy scipy Pillow scikit-learn opencv-python-headless matplotlib pytest)

install_python_packages() {
  # (a) a virtualenv is the cleanest answer when one already exists
  if [ -n "${VIRTUAL_ENV:-}" ]; then
    pip install -q "$@" && return 0
  fi
  # (b) pipx is for applications, not libraries; try it only for tools
  # (c) the documented override for PEP 668 systems
  if pip3 install -q --break-system-packages "$@" 2>/dev/null; then
    echo "  installed via pip3 --break-system-packages"
    return 0
  fi
  # (d) pre-PEP-668 systems
  if pip3 install -q --user "$@" 2>/dev/null; then
    echo "  installed via pip3 --user"
    return 0
  fi
  return 1
}

if install_python_packages "${PY_PKGS[@]}"; then
  echo "  python stack ready"
else
  warn "python packages could not be installed automatically."
  warn "Create a virtualenv and install requirements.txt into it:"
  warn "    python3 -m venv .venv && . .venv/bin/activate"
  warn "    pip install -r requirements.txt"
fi

# ---------------------------------------------------------------- layer 3

if [ "${INSTALL_RUST:-0}" = "1" ]; then
  note "layer 3a: rust (stegscan sideline)"
  if command -v cargo >/dev/null; then
    echo "  cargo already present: $(cargo -V)"
  elif [ -n "$SUDO" ] || [ "$(id -u)" -eq 0 ]; then
    $SUDO apt-get install $APT_YES -qq rustc cargo >/dev/null 2>&1 \
      && echo "  installed rustc/cargo from apt" \
      || warn "install Rust from https://rustup.rs instead"
  fi
fi

if [ "${INSTALL_OPTIONAL:-0}" = "1" ]; then
  note "layer 3b: optional tooling"

  if command -v gem >/dev/null; then
    $SUDO gem install zsteg --no-document >/dev/null 2>&1 \
      && echo "  installed zsteg" || warn "zsteg install failed"
  else
    warn "ruby/gem not present; skipping zsteg"
  fi

  if ! command -v stegseek >/dev/null; then
    warn "stegseek is not packaged in Kali; install the .deb from"
    warn "  https://github.com/RickdeJager/stegseek/releases"
    warn "  (see also the stegseek-rs reimplementation referenced in RESOURCES.md)"
  fi

  if install_python_packages stegoveritas aletheia-steg 2>/dev/null; then
    echo "  installed stegoveritas / aletheia"
  else
    warn "stegoveritas / aletheia not installed; both are optional for P0"
  fi
fi

if [ "${INSTALL_ML:-0}" = "1" ]; then
  note "layer 3c: deep-learning stack (chapter T6)"
  warn "PyTorch is a multi-gigabyte download. CPU-only wheel:"
  warn "    pip3 install torch --index-url https://download.pytorch.org/whl/cpu"
  warn "Not installed automatically -- pick the build that matches your hardware."
fi

# ------------------------------------------------------------------ verify

note "verification"
if [ -f scripts/verify-toolchain.sh ]; then
  bash scripts/verify-toolchain.sh
else
  warn "run scripts/verify-toolchain.sh from the repository root"
fi
