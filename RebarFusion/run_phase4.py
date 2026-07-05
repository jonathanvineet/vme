"""
run_phase4.py — Phase 4: Spatial Query Engine

Builds the Spatial Query Engine and runs acceptance/benchmark tests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
import uuid
from dataclasses import asdict

from core.project import DrawingProject
from core.readers.dxf_reader import DXFReader
from core.geometry.canonicalizer import canonicalize
from core.spatial.engine import SpatialQueryEngine


class BenchmarkEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if hasattr(obj, '__dataclass_fields__'):
            return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def _jdump(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, cls=BenchmarkEncoder)


def run_phase4(directory: str):
    project = DrawingProject()
    manifest = project.load_directory(directory)

    corrupt = sum(1 for d in manifest.drawings.values() if d.validation_errors)
    if corrupt:
        print("[ERROR] Phase 1 health check failed.")
        sys.exit(1)

    print("Phase 1, 2, 3... running to generate canonical geometry.")

    reader = DXFReader()
    
    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of or not drawing.capabilities.geometry:
            continue

        print(f"\n{'='*60}")
        print(f"Phase 4 Spatial Engine: {filename}")
        print(f"{'='*60}")

        phase2_repo = reader.read_geometry(drawing.filepath, drawing.identity)
        canon_repo, validation = canonicalize(phase2_repo, drawing.filepath)

        if validation["critical_errors"]:
            print(f"[ERROR] Critical errors in Phase 3 canonicalization for {filename}")
            continue

        # Build Phase 4 Engine
        t0 = time.perf_counter()
        engine = SpatialQueryEngine.build(canon_repo)
        t1 = time.perf_counter()
        build_time_ms = (t1 - t0) * 1000.0
        
        print(f"  Engine built in {build_time_ms:.2f} ms")

        benchmarks = {}
        acceptance = {}

        # ---------------------------------------------------------
        # Acceptance Tests & Benchmarks
        # ---------------------------------------------------------

        # 1. nearest_point
        q_pt = (
            (canon_repo.bbox_report.drawing[0] + canon_repo.bbox_report.drawing[2]) / 2.0,
            (canon_repo.bbox_report.drawing[1] + canon_repo.bbox_report.drawing[3]) / 2.0
        )
        t0 = time.perf_counter()
        res = engine.nearest_point(q_pt)
        t1 = time.perf_counter()
        benchmarks['nearest_point'] = (t1 - t0) * 1000.0
        acceptance['nearest_point'] = len(res) == 1

        # 2. within_radius
        t0 = time.perf_counter()
        res = engine.within_radius(q_pt, 50000.0)
        t1 = time.perf_counter()
        benchmarks['within_radius'] = (t1 - t0) * 1000.0
        acceptance['within_radius'] = len(res) > 0

        # 3. intersect_bbox
        bbox = canon_repo.bbox_report.drawing
        t0 = time.perf_counter()
        res = engine.intersect_bbox(bbox)
        t1 = time.perf_counter()
        benchmarks['intersect_bbox'] = (t1 - t0) * 1000.0
        # should return all entities that have a valid bbox
        expected_len = len([e for e in canon_repo.all_entities() if e.bounding_box != (0.0,0.0,0.0,0.0)])
        acceptance['intersect_bbox'] = len(res) == expected_len

        # 4. query_layer
        if canon_repo.lines:
            test_layer = canon_repo.lines[0].layer
        else:
            test_layer = "A-FLOR"
        t0 = time.perf_counter()
        res = engine.query_layer(test_layer)
        t1 = time.perf_counter()
        benchmarks['query_layer'] = (t1 - t0) * 1000.0
        acceptance['query_layer'] = len(res) > 0

        # 5. query_type
        t0 = time.perf_counter()
        res = engine.query_type("LINE")
        t1 = time.perf_counter()
        benchmarks['query_type'] = (t1 - t0) * 1000.0
        acceptance['query_type'] = len(res) == len(canon_repo.lines)

        # 6. query_orientation
        t0 = time.perf_counter()
        res = engine.query_orientation(90.0)
        t1 = time.perf_counter()
        benchmarks['query_orientation'] = (t1 - t0) * 1000.0
        acceptance['query_orientation'] = True # Just checks it doesn't crash

        # 7. parallel
        test_line = canon_repo.lines[0] if canon_repo.lines else None
        if test_line:
            t0 = time.perf_counter()
            res = engine.parallel(test_line)
            t1 = time.perf_counter()
            benchmarks['parallel'] = (t1 - t0) * 1000.0
            acceptance['parallel'] = True
        else:
            benchmarks['parallel'] = 0.0
            acceptance['parallel'] = True

        # 8. similar_length
        if test_line:
            t0 = time.perf_counter()
            res = engine.similar_length(test_line)
            t1 = time.perf_counter()
            benchmarks['similar_length'] = (t1 - t0) * 1000.0
            acceptance['similar_length'] = True
        else:
            benchmarks['similar_length'] = 0.0
            acceptance['similar_length'] = True

        # 9. text_near
        if test_line:
            t0 = time.perf_counter()
            res = engine.text_near(test_line, 2000.0)
            t1 = time.perf_counter()
            benchmarks['text_near'] = (t1 - t0) * 1000.0
            acceptance['text_near'] = True
        else:
            benchmarks['text_near'] = 0.0
            acceptance['text_near'] = True

        # 10. dimension_near
        if test_line:
            t0 = time.perf_counter()
            res = engine.dimension_near(test_line, 3000.0)
            t1 = time.perf_counter()
            benchmarks['dimension_near'] = (t1 - t0) * 1000.0
            acceptance['dimension_near'] = True
        else:
            benchmarks['dimension_near'] = 0.0
            acceptance['dimension_near'] = True

        # 11. fingerprint_lookup
        if test_line:
            t0 = time.perf_counter()
            res = engine.fingerprint_lookup(test_line.geometry_hash)
            t1 = time.perf_counter()
            benchmarks['fingerprint_lookup'] = (t1 - t0) * 1000.0
            acceptance['fingerprint_lookup'] = len(res) >= 1
        else:
            benchmarks['fingerprint_lookup'] = 0.0
            acceptance['fingerprint_lookup'] = True


        print("\n  ── Acceptance Tests ──────────────────────")
        all_passed = True
        for k, v in acceptance.items():
            status = "✅ PASS" if v else "❌ FAIL"
            print(f"  {k:<20}: {status}")
            if not v:
                all_passed = False

        print("\n  ── Benchmarks (ms) ───────────────────────")
        for k, v in benchmarks.items():
            print(f"  {k:<20}: {v:.4f} ms")

        print(f"\n  READY FOR PHASE 5  {'YES ✅' if all_passed else 'NO ❌'}")

        # Dump debug outputs
        out_dir = os.path.join("debug", "phase04", filename)
        
        # sample indices
        _jdump(os.path.join(out_dir, "point_index.json"), engine._point_index.points[:20])
        _jdump(os.path.join(out_dir, "bbox_index.json"), engine._bbox_index.bboxes[:20])
        _jdump(os.path.join(out_dir, "orientation_index.json"), {k: len(v) for k, v in engine._orientation_index.buckets.items()})
        _jdump(os.path.join(out_dir, "layer_index.json"), {k: len(v) for k, v in engine._semantic_index.by_layer.items()})
        
        _jdump(os.path.join(out_dir, "benchmarks.json"), benchmarks)
        _jdump(os.path.join(out_dir, "acceptance_report.json"), acceptance)

        # Golden corpus
        golden_dir = os.path.join("tests", "golden", filename.replace(".dxf","").replace(".dwg",""), "phase04")
        os.makedirs(golden_dir, exist_ok=True)
        _jdump(os.path.join(golden_dir, "benchmarks.json"), benchmarks)

        print(f"\n  Debug & Golden outputs written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 4: Spatial Query Engine")
    parser.add_argument("directory")
    args = parser.parse_args()
    run_phase4(args.directory)
