"""
tests/regression.py

Regression test suite. Compares current Phase 2 & 3 outputs against golden
snapshots written when the phase was first frozen.

Usage:
    python tests/regression.py <directory>

Exit codes:
    0  — all checks pass
    1  — one or more regressions detected
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

GOLDEN_ROOT = os.path.join(os.path.dirname(__file__), "golden")


def _load(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def _check_counts(name: str, current: Dict, golden: Dict, failures: list):
    for k, v in golden.items():
        cur = current.get(k, -1)
        if cur != v:
            failures.append(f"  [{name}] {k}: golden={v}  current={cur}  DRIFT={cur-v:+d}")


def _check_bbox(name: str, current: list, golden: list, failures: list, tol: float = 1.0):
    if len(current) != 4 or len(golden) != 4:
        failures.append(f"  [{name}] Bounding box malformed")
        return
    for i, (c, g) in enumerate(zip(current, golden)):
        if abs(c - g) > tol:
            label = ["min_x","min_y","max_x","max_y"][i]
            failures.append(f"  [{name}] bbox.{label}: golden={g:.3f} current={c:.3f} delta={c-g:+.3f}")


def _check_fingerprints(name: str, current: Dict, golden: Dict, failures: list):
    # Compare by hash values (sets), not UUIDs — UUIDs for exploded entities
    # are derived from the drawing identity UUID which is re-generated each project load.
    golden_hashes  = set(golden.values())
    current_hashes = set(current.values())

    missing = golden_hashes - current_hashes
    added   = current_hashes - golden_hashes

    if missing:
        failures.append(f"  [{name}] {len(missing)} geometry fingerprints disappeared (geometry was removed or altered)")
    if added:
        # New geometry is informational only
        print(f"  [{name}] INFO: {len(added)} new geometry fingerprints added since golden")


def run_regression(directory: str) -> int:
    """Returns 0 on pass, 1 on failure."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from core.project import DrawingProject
    from core.readers.dxf_reader import DXFReader
    from core.geometry.canonicalizer import canonicalize
    from core.spatial.engine import SpatialQueryEngine

    project = DrawingProject()
    manifest = project.load_directory(directory)
    reader = DXFReader()

    all_failures = []

    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of or not drawing.capabilities.geometry:
            continue

        drawing_key = filename.replace(".dxf", "").replace(".dwg", "")
        golden_base = os.path.join(GOLDEN_ROOT, drawing_key)

        if not os.path.isdir(golden_base):
            print(f"  SKIP {filename}: No golden snapshot found at {golden_base}")
            continue

        print(f"\nRegression: {filename}")

        # Phase 2
        phase2_repo = reader.read_geometry(drawing.filepath, drawing.identity)
        phase2_report = phase2_repo.generate_translation_report()

        p2_golden_path = os.path.join(golden_base, "phase02", "translation_report.json")
        if os.path.exists(p2_golden_path):
            p2_golden = _load(p2_golden_path)
            failures = []
            _check_counts(f"{filename}/phase02", phase2_report, p2_golden, failures)
            if failures:
                all_failures.extend(failures)
                for f in failures:
                    print(f"  ❌ {f}")
            else:
                print(f"  Phase 2 counts  ✅")
        else:
            print(f"  Phase 2 golden missing — skipping count check")

        # Phase 3
        canon_repo, validation = canonicalize(phase2_repo, drawing.filepath)

        p3_golden_dir = os.path.join(golden_base, "phase03")

        # counts
        counts_path = os.path.join(p3_golden_dir, "canonical_counts.json")
        if os.path.exists(counts_path):
            p3_golden_counts = _load(counts_path)
            failures = []
            _check_counts(f"{filename}/phase03/counts", canon_repo.counts(), p3_golden_counts, failures)
            if failures:
                all_failures.extend(failures)
                for f in failures:
                    print(f"  ❌ {f}")
            else:
                print(f"  Phase 3 counts  ✅")

        # bbox
        bbox_path = os.path.join(p3_golden_dir, "bbox_drawing.json")
        if os.path.exists(bbox_path):
            golden_bbox = _load(bbox_path)["bbox"]
            failures = []
            _check_bbox(f"{filename}/phase03/bbox", list(canon_repo.bbox_report.drawing), golden_bbox, failures)
            if failures:
                all_failures.extend(failures)
                for f in failures:
                    print(f"  ❌ {f}")
            else:
                print(f"  Phase 3 bbox    ✅")

        # fingerprints
        fp_path = os.path.join(p3_golden_dir, "entity_fingerprints.json")
        if os.path.exists(fp_path):
            golden_fps = _load(fp_path)
            current_fps = {str(e.id): e.geometry_hash for e in canon_repo.all_entities()}
            failures = []
            _check_fingerprints(f"{filename}/phase03/fingerprints", current_fps, golden_fps, failures)
            if failures:
                all_failures.extend(failures)
                for f in failures:
                    print(f"  ❌ {f}")
            else:
                print(f"  Phase 3 fingerprints ✅")

        # Phase 4 (stub for completeness, benchmarks normally aren't regressed strictly)
        # Phase 5 & 6
        from core.topology.node_builder import build_nodes
        from core.topology.builder import TopologyBuilder
        engine = SpatialQueryEngine.build(canon_repo)
        node_repo, _, _ = build_nodes(canon_repo, engine, filename)
        builder = TopologyBuilder(node_repo, canon_repo)
        graph, comp_repo, metrics, validation6 = builder.build()
        
        p6_golden_dir = os.path.join(golden_base, "phase06")
        
        # metrics
        metrics_path = os.path.join(p6_golden_dir, "metrics.json")
        if os.path.exists(metrics_path):
            p6_golden_metrics = _load(metrics_path)
            failures = []
            _check_counts(f"{filename}/phase06/metrics", metrics, p6_golden_metrics, failures)
            if failures:
                all_failures.extend(failures)
                for f in failures:
                    print(f"  ❌ {f}")
            else:
                print(f"  Phase 6 metrics ✅")
                
        # component UUID stability
        comps_path = os.path.join(p6_golden_dir, "components.json")
        if os.path.exists(comps_path):
            golden_comps = _load(comps_path)
            current_comp_uuids = set(str(k) for k in comp_repo.components.keys())
            golden_comp_uuids = set(golden_comps.keys())
            
            missing_comps = golden_comp_uuids - current_comp_uuids
            added_comps = current_comp_uuids - golden_comp_uuids
            
            if missing_comps:
                all_failures.append(f"  [{filename}/phase06/components] {len(missing_comps)} topological components disappeared or changed UUIDs")
                print(f"  ❌ [{filename}/phase06/components] {len(missing_comps)} components drifted")
            else:
                print(f"  Phase 6 component stability ✅")
            
            if added_comps:
                print(f"  [{filename}/phase06/components] INFO: {len(added_comps)} new components created")

        if validation6["critical_errors"]:
            all_failures.append(f"  [{filename}] Phase 6 validation has critical errors")
        if validation6["errors"]:
            all_failures.append(f"  [{filename}] Phase 6 validation has {len(validation6['errors'])} error(s): {validation6['errors'][:3]}")
        else:
            print(f"  Phase 6 validation (errors) ✅")

        # Phase 7
        from core.recognition.registry import RecognizerRegistry
        from core.recognition.recognizers import (
            StraightBarRecognizer, LBarRecognizer, UBarRecognizer, ClosedShapeRecognizer,
            BranchRecognizer, DimensionRecognizer, LeaderRecognizer,
            StructuralOutlineRecognizer
        )
        registry = RecognizerRegistry()
        registry.register(StraightBarRecognizer())
        registry.register(LBarRecognizer())
        registry.register(UBarRecognizer())
        registry.register(ClosedShapeRecognizer())
        registry.register(BranchRecognizer())
        registry.register(StructuralOutlineRecognizer())
        registry.register(DimensionRecognizer())
        registry.register(LeaderRecognizer())

        p7_golden_dir = os.path.join(golden_base, "phase07")
        recog_path = os.path.join(p7_golden_dir, "recognition_results.json")
        if os.path.exists(recog_path):
            golden_recog = _load(recog_path)
            current_recog = {}
            for comp in comp_repo.components.values():
                res = registry.evaluate(comp, graph)
                current_recog[str(comp.id)] = res

            failures = []
            for cid, g_res in golden_recog.items():
                if cid not in current_recog:
                    failures.append(f"Component {cid} disappeared.")
                    continue
                c_res = current_recog[cid]
                if c_res.label != g_res['label']:
                    failures.append(f"Comp {cid}: label changed {g_res['label']} -> {c_res.label}")
                if c_res.fingerprint != g_res['fingerprint']:
                    failures.append(f"Comp {cid}: fingerprint changed {g_res['fingerprint']} -> {c_res.fingerprint}")

            if failures:
                all_failures.extend([f"  [{filename}/phase07/recognition] {f}" for f in failures[:5]])
                print(f"  ❌ [{filename}/phase07] {len(failures)} recognition drifts")
            else:
                print(f"  Phase 7 recognition ✅")

    print("\n" + "=" * 60)
    if all_failures:
        print(f"REGRESSION FAILED — {len(all_failures)} issue(s) detected:")
        for f in all_failures:
            print(f)
        return 1
    else:
        print("REGRESSION PASSED — All golden checks match ✅")
        return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/regression.py <directory>")
        sys.exit(1)
    sys.exit(run_regression(sys.argv[1]))
