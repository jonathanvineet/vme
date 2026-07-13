#!/bin/zsh
# scripts/setup_oda.sh — obtain the ODA File Converter for DWG ingestion.
#
# The converter is NOT committed to this repository (149MB, and ODA's
# freeware EULA does not permit redistribution). This script checks for a
# working copy and, if absent, walks you through obtaining the exact
# version the pipeline was validated against.
#
# Pinned version: ODA File Converter 27.1.0.0 (validated in
# docs/audits/phase13/13.0_dwg_ingestion.md — canonical-level determinism
# was verified against this version specifically; a different version may
# work but has not been validated).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_BIN="$REPO_ROOT/tools/oda/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"
BIN="${RF_ODA_CONVERTER:-$DEFAULT_BIN}"

if [[ -x "$BIN" ]]; then
    echo "OK: ODA File Converter present at:"
    echo "    $BIN"
    exit 0
fi

cat <<'EOF'
ODA File Converter not found.

Required version: 27.1.0.0 (later versions untested)

To install (no admin rights / no system-wide install needed):

  1. Download the macOS package from the official ODA page:
         https://www.opendesign.com/guestfiles/oda_file_converter
     Pick the .pkg matching your CPU (arm64 for Apple Silicon).
     Downloading requires accepting ODA's license terms on their site.

  2. Extract it locally (do NOT run the installer):
         pkgutil --expand ODAFileConverter_*.pkg /tmp/oda_expanded
         mkdir -p /tmp/oda_payload && cd /tmp/oda_payload
         gzip -dc /tmp/oda_expanded/Payload | cpio -i

  3. Place the app bundle into this repo (gitignored):
         mkdir -p <repo>/tools/oda
         cp -R /tmp/oda_payload/ODAFileConverter.app <repo>/tools/oda/

  4. Re-run this script to verify.

Alternatively, set RF_ODA_CONVERTER to the path of an existing
ODAFileConverter binary anywhere on this machine.

Without the converter, .dwg files are skipped with a "No reader
available" warning; .dxf ingestion is unaffected.
EOF
exit 1
