"""
core/readers/dwg_converter.py — DWG -> DXF conversion via ODA File Converter.

This module's ONLY responsibility is producing a DXF file from a DWG file.
It is deliberately not a parser: the converted DXF is handed to the
already-audited DXFReader (core/readers/dxf_reader.py), so there is exactly
one geometry-extraction path in the pipeline regardless of input format.
See docs/audits/phase13/13.0_dwg_ingestion.md.

Converter binary: ODA File Converter 27.1.0.0 (Open Design Alliance,
free distribution), extracted locally into tools/oda/ — NOT installed
system-wide, so the exact converter version travels with the repo checkout.
Override the binary location with the RF_ODA_CONVERTER env var.

Determinism note (verified before this module was written): converting the
same DWG twice produces DXF output that is byte-identical EXCEPT for the
$TDUPDATE/$TDUUPDATE header timestamps, which ODA stamps with the
conversion time. The canonicalization pipeline never reads those header
variables, so canonical geometry derived from a converted file is
deterministic. Conversions are cached by the DWG's SHA-256, so a drawing
is converted once per content-version, not once per run — which also makes
the cached DXF itself byte-stable across runs.

The cache lives OUTSIDE the project directory (in the user cache dir):
Phase 1's load_directory() os.walk()s the project directory recursively,
and a cache subfolder of converted .dxf files would be scanned as new,
duplicate drawings.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile

# ACAD2018 = DXF R2018 (AC1032) — a version ezdxf reads natively; the same
# output version was used for the manual verification runs this module's
# determinism notes are based on.
_OUTPUT_VERSION = "ACAD2018"
_CONVERT_TIMEOUT_S = 300


class DWGConversionError(RuntimeError):
    pass


def _default_converter_path() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(
        repo_root, "tools", "oda",
        "ODAFileConverter.app", "Contents", "MacOS", "ODAFileConverter",
    )


def converter_path() -> str:
    return os.environ.get("RF_ODA_CONVERTER", _default_converter_path())


def converter_available() -> bool:
    path = converter_path()
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _cache_dir() -> str:
    base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    path = os.path.join(base, "rebarfusion", "dwg2dxf")
    os.makedirs(path, exist_ok=True)
    return path


def _file_sha256(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def convert_dwg_to_dxf(dwg_path: str) -> str:
    """Returns the path of a DXF equivalent of `dwg_path`, converting via
    ODA File Converter on first call and serving from the checksum-keyed
    cache afterwards. Raises DWGConversionError if the converter is
    missing or the conversion produces no output."""
    if not converter_available():
        raise DWGConversionError(
            f"ODA File Converter not found at {converter_path()!r} "
            f"(set RF_ODA_CONVERTER or extract it into tools/oda/)"
        )

    checksum = _file_sha256(dwg_path)
    cached = os.path.join(_cache_dir(), f"{checksum}.dxf")
    if os.path.isfile(cached):
        return cached

    # ODA's CLI is batch-only (input dir -> output dir), so single-file
    # conversion means staging the one file alone in a temp directory.
    basename = os.path.basename(dwg_path)
    stem = os.path.splitext(basename)[0]
    with tempfile.TemporaryDirectory(prefix="rf_dwg_in_") as in_dir, \
         tempfile.TemporaryDirectory(prefix="rf_dwg_out_") as out_dir:
        shutil.copy2(dwg_path, os.path.join(in_dir, basename))
        try:
            subprocess.run(
                [converter_path(), in_dir, out_dir, _OUTPUT_VERSION, "DXF", "0", "1", "*.dwg"],
                capture_output=True, timeout=_CONVERT_TIMEOUT_S, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DWGConversionError(f"conversion of {basename!r} timed out") from exc

        produced = os.path.join(out_dir, f"{stem}.dxf")
        if not os.path.isfile(produced) or os.path.getsize(produced) == 0:
            # ODA writes a per-run error log into the output dir on failure
            errors = [f for f in os.listdir(out_dir) if f.endswith(".err")]
            detail = ""
            if errors:
                with open(os.path.join(out_dir, errors[0]), "r", errors="replace") as f:
                    detail = f": {f.read(500)}"
            raise DWGConversionError(f"conversion of {basename!r} produced no DXF{detail}")

        shutil.move(produced, cached)

    return cached
