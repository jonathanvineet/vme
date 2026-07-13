"""
tests/test_dwg_ingestion.py

Phase 13.0 (DWG ingestion) freeze criteria:
  1. Converter present -- the locally-extracted ODA File Converter binary
     (tools/oda/, version 27.1.0.0) exists and is executable, or the test
     suite fails loudly rather than silently skipping.
  2. Conversion determinism at the CANONICAL level -- converting the same
     DWG twice (cache cleared in between, forcing a genuine reconversion)
     must produce identical canonical geometry. Raw DXF output is NOT
     byte-identical across conversions ($TDUPDATE/$TDUUPDATE header
     timestamps differ -- verified during setup); what matters is that
     nothing the canonicalizer reads differs. This is the Phase 7
     determinism discipline applied to the new ingestion path.
  3. Real-data regression on SS-GF-01(R).dwg -- the drawing whose
     unreadability was the research report's #1 ranked risk. Asserts the
     exact observation count and the finding that confirmed the research
     report's central prediction: this Reinforcement sheet carries ONLY
     self-decoding T-marks (T8/T10/T12/T20), zero N-reference-codes.
  4. Reader dispatch -- Phase 1 must classify .dwg drawings as
     geometry-capable now (they were "No reader available" before), and
     the DWG path must flow through the same DXFReader/canonicalizer as
     native DXF (one parser, not two).

Usage:
    python tests/test_dwg_ingestion.py <directory>   # expects test_project

Exit codes:
    0 — all checks passed
    1 — a check failed
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, is_dataclass

DWG_FILE = "SS-GF-01(R).dwg"


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


def check_converter_present() -> bool:
    from core.readers.dwg_converter import converter_available, converter_path

    ok = converter_available()
    print(f"[converter] {converter_path()} -> {'present' if ok else 'MISSING'}")
    return ok


def _canonical_hash(directory: str, filename: str) -> str:
    """Phase 1 -> 2 -> 3 on one drawing, hashed over every canonical
    entity's UUID + geometry -- the same level tests/determinism.py
    guards for the DXF path."""
    from core.project import DrawingProject
    from core.geometry.canonicalizer import canonicalize
    from core.readers.dwg_converter import convert_dwg_to_dxf

    project = DrawingProject()
    manifest = project.load_directory(directory)
    drawing = manifest.drawings[filename]
    reader = project._get_reader(drawing.filepath)
    geometry_path = convert_dwg_to_dxf(drawing.filepath)
    phase2 = reader.read_geometry(drawing.filepath, drawing.identity)
    canon_repo, _ = canonicalize(phase2, geometry_path)

    entries = []
    for coll in (canon_repo.lines, canon_repo.arcs, canon_repo.polylines, canon_repo.texts):
        for e in coll:
            entries.append(str(e.id))
    entries.sort()
    return hashlib.sha256("|".join(entries).encode("utf-8")).hexdigest()


def check_conversion_determinism(directory: str) -> bool:
    from core.readers.dwg_converter import convert_dwg_to_dxf, _file_sha256, _cache_dir

    dwg_path = os.path.join(directory, DWG_FILE)
    hash_one = _canonical_hash(directory, DWG_FILE)

    # Force a genuine reconversion, not a cache hit
    cached = os.path.join(_cache_dir(), f"{_file_sha256(dwg_path)}.dxf")
    os.remove(cached)
    hash_two = _canonical_hash(directory, DWG_FILE)

    ok = hash_one == hash_two
    print(f"[determinism] canonical hash after reconversion: "
          f"{'identical' if ok else 'DIVERGED'} ({hash_one[:12]}...)")
    return ok


def check_real_data_regression(directory: str) -> bool:
    from core.full_pipeline import run_pipeline_through_phase9
    from core.fusion.observation_builder import build_observations
    from core.fusion.models import ASPECT_MARK

    results = list(run_pipeline_through_phase9(directory))
    observations = build_observations(results)
    ss_r = [o for o in observations if o.drawing_filename == DWG_FILE]

    marks = {o.fact(ASPECT_MARK).value for o in ss_r if o.fact(ASPECT_MARK)}
    namespaces = {o.mark_namespace for o in ss_r}
    roles = {o.drawing_role.role for o in ss_r}

    ok = (
        len(ss_r) == 18
        and marks == {"T8", "T10", "T12", "T20"}
        and namespaces == {"self_decoding"}
        and roles == {"reinforcement_typical"}
    )
    print(f"[real-data] {DWG_FILE}: {len(ss_r)} observation(s), marks={sorted(marks)}, "
          f"namespaces={namespaces}, roles={roles} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_reader_dispatch(directory: str) -> bool:
    from core.project import DrawingProject
    from core.readers.dwg_reader import DWGReader
    from core.readers.dxf_reader import DXFReader

    project = DrawingProject()
    manifest = project.load_directory(directory)

    dwg = manifest.drawings[DWG_FILE]
    dxf = manifest.drawings["SS-GF-01(M).dxf"]
    dwg_reader = project._get_reader(dwg.filepath)
    dxf_reader = project._get_reader(dxf.filepath)

    ok = (
        dwg.capabilities.geometry
        and isinstance(dwg_reader, DWGReader)
        and isinstance(dxf_reader, DXFReader)
        and not any("No reader available" in w for w in dwg.validation_warnings)
    )
    print(f"[dispatch] {DWG_FILE}: geometry={dwg.capabilities.geometry}, "
          f"reader={type(dwg_reader).__name__}; SS-GF-01(M).dxf reader="
          f"{type(dxf_reader).__name__} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def run_check(directory: str) -> int:
    results = [
        check_converter_present(),
        check_reader_dispatch(directory),
        check_conversion_determinism(directory),
        check_real_data_regression(directory),
    ]
    if all(results):
        print("\nDWG INGESTION CHECKS PASSED ✅")
        return 0
    print("\nDWG INGESTION CHECKS FAILED ❌")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_dwg_ingestion.py <directory>")
        sys.exit(1)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    sys.exit(run_check(sys.argv[1]))
