#!/usr/bin/env bash
# Bootstrap a brand-new macOS machine (no Homebrew, no Python, nothing)
# so it can run the face-recognition attendance system.
#
# Usage:
#   cd facerecog
#   ./setup.sh
#
# Safe to re-run — every step checks whether it's already done.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "This script targets macOS. On Linux, install python3, cmake, build-essential, libopenblas-dev via your package manager, then run: pip3 install -r requirements.txt"
fi

# 1. Xcode Command Line Tools (needed to compile dlib)
if ! xcode-select -p >/dev/null 2>&1; then
  log "Installing Xcode Command Line Tools (a GUI installer window will pop up — click Install, then re-run this script when it finishes)"
  xcode-select --install
  fail "Re-run ./setup.sh once the Command Line Tools install finishes."
else
  log "Xcode Command Line Tools already installed"
fi

# 2. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  log "Installing Homebrew"
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || fail "Homebrew install failed. See https://brew.sh for manual steps."
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
else
  log "Homebrew already installed"
  eval "$(brew shellenv)"
fi

# 3. python3 + cmake (cmake is required to build dlib from source)
for pkg in python cmake; do
  if brew list "$pkg" >/dev/null 2>&1; then
    log "$pkg already installed (brew)"
  else
    log "Installing $pkg"
    brew install "$pkg" || fail "brew install $pkg failed"
  fi
done

command -v python3 >/dev/null 2>&1 || fail "python3 still not on PATH after installing — open a new terminal and re-run ./setup.sh"

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
log "Using python3 ($PYVER)"

# 4. Virtual environment (keeps this project's packages isolated)
if [[ ! -d .venv ]]; then
  log "Creating virtual environment (.venv)"
  python3 -m venv .venv || fail "python3 -m venv failed"
else
  log "Virtual environment already exists"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

log "Upgrading pip/setuptools/wheel"
pip install --upgrade pip setuptools wheel >/dev/null

# 5. Project dependencies (dlib will compile from source here — can take 5-15 min)
log "Installing Python packages from requirements.txt (dlib compiles from source; this can take a while, please be patient)"
pip install -r requirements.txt || fail "pip install -r requirements.txt failed — see the error above"

log "Done. Activate the environment in future shells with:  source .venv/bin/activate"
log "Then start everything with:  ./start_all.sh"
