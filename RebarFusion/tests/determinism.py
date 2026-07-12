"""
tests/determinism.py

Runs the full pipeline (Phase 1 -> Phase 7 recognition) N times on the same
drawing and asserts every run produces an identical recognition-result hash.
This guards against the class of bug found in the Phase 7.1 determinism
audit: canonical entity UUIDs derived from a randomly-regenerated per-load
"drawing identity" UUID, which made set/dict iteration order (and therefore
float-summation order in component statistics) vary run-to-run even though
the geometry itself was unchanged.

Usage:
    python tests/determinism.py <directory> [--runs N]

Exit codes:
    0 — all N runs produced an identical hash
    1 — nondeterminism detected
"""

from __future__ import annotations

import hashlib
import json
import os
import sys


def run_once(directory: str, filename: str) -> dict:
    from core.project import DrawingProject
    from core.readers.dxf_reader import DXFReader
    from core.geometry.canonicalizer import canonicalize
    from core.spatial.engine import SpatialQueryEngine
    from core.topology.node_builder import build_nodes
    from core.topology.builder import TopologyBuilder
    from core.recognition.registry import RecognizerRegistry
    from core.recognition.recognizers import (
        StraightBarRecognizer, LBarRecognizer, UBarRecognizer, ClosedShapeRecognizer,
        BranchRecognizer, DimensionRecognizer, LeaderRecognizer, StructuralOutlineRecognizer
    )

    project = DrawingProject()
    manifest = project.load_directory(directory)
    drawing = manifest.drawings[filename]
    reader = DXFReader()
    phase2_repo = reader.read_geometry(drawing.filepath, drawing.identity)
    canon_repo, _ = canonicalize(phase2_repo, drawing.filepath)
    engine = SpatialQueryEngine.build(canon_repo)
    node_repo, _, _ = build_nodes(canon_repo, engine, filename)
    builder = TopologyBuilder(node_repo, canon_repo)
    graph, comp_repo, metrics, validation = builder.build()

    registry = RecognizerRegistry()
    registry.register(StraightBarRecognizer())
    registry.register(LBarRecognizer())
    registry.register(UBarRecognizer())
    registry.register(ClosedShapeRecognizer())
    registry.register(BranchRecognizer())
    registry.register(StructuralOutlineRecognizer())
    registry.register(DimensionRecognizer())
    registry.register(LeaderRecognizer())

    results = {}
    for cid, comp in comp_repo.components.items():
        res = registry.evaluate(comp, graph)
        results[str(cid)] = {
            "label": res.label,
            "fingerprint": res.fingerprint,
            "measurements": res.measurements,
        }
    return results


def run_determinism_check(directory: str, filename: str, runs: int = 10) -> int:
    hashes = []
    all_results = []
    for i in range(runs):
        r = run_once(directory, filename)
        blob = json.dumps(r, sort_keys=True).encode("utf-8")
        h = hashlib.sha256(blob).hexdigest()
        hashes.append(h)
        all_results.append(r)
        print(f"  run {i + 1:2d}/{runs}: {h}")

    unique = set(hashes)
    print(f"\nunique hashes: {len(unique)} / {runs} runs")

    if len(unique) == 1:
        print("DETERMINISM CHECK PASSED — identical output on every run ✅")
        return 0

    print("DETERMINISM CHECK FAILED — output varies across identical runs ❌\n")
    base = all_results[0]
    for i, r in enumerate(all_results[1:], start=2):
        diffs = [(cid, v, r.get(cid)) for cid, v in base.items() if r.get(cid) != v]
        if diffs:
            print(f"run 1 vs run {i}: {len(diffs)} component(s) differ")
            for cid, old, new in diffs[:10]:
                print(f"  component {cid}")
                print(f"    old: {old}")
                print(f"    new: {new}")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/determinism.py <directory> [--runs N] [--file FILENAME]")
        sys.exit(1)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    directory = sys.argv[1]
    runs = 10
    filename = "SS-GF-01(M).dxf"
    if "--runs" in sys.argv:
        runs = int(sys.argv[sys.argv.index("--runs") + 1])
    if "--file" in sys.argv:
        filename = sys.argv[sys.argv.index("--file") + 1]

    sys.exit(run_determinism_check(directory, filename, runs))
