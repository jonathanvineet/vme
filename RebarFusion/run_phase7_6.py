"""
run_phase7_6.py — Phase 7.6: Physical Plausibility Engine

Usage:
    python run_phase7_6.py <directory>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict

from core.project import DrawingProject
from core.readers.dxf_reader import DXFReader
from core.geometry.canonicalizer import canonicalize
from core.spatial.engine import SpatialQueryEngine
from core.topology.node_builder import build_nodes
from core.topology.builder import TopologyBuilder
from core.recognition.registry import RecognizerRegistry, RecognitionCache
from core.recognition.recognizers import (
    StraightBarRecognizer, LBarRecognizer, UBarRecognizer, ClosedShapeRecognizer,
    BranchRecognizer, DimensionRecognizer, LeaderRecognizer,
    StructuralOutlineRecognizer
)
from core.recognition.plausibility import evaluate_plausibility

BAR_SHAPE_LABELS = {"straight_bar", "l_bar", "u_bar", "stirrup", "branch"}


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


def _jdump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, cls=UUIDEncoder)


def build_plausibility_records(comp_repo, cache):
    records = {}
    for cid, comp in comp_repo.components.items():
        result = cache.get(cid)
        if not result or result.label not in BAR_SHAPE_LABELS:
            continue
        length = float(comp.statistics.get("total_length", 0.0))
        records[cid] = {"label": result.label, "length": length}
    return records


def main():
    parser = argparse.ArgumentParser(description="Phase 7.6: Physical Plausibility Engine")
    parser.add_argument("directory")
    args = parser.parse_args()

    project = DrawingProject()
    manifest = project.load_directory(args.directory)

    print("=" * 60)
    print("PHASE 7.6: PHYSICAL PLAUSIBILITY ENGINE")
    print("=" * 60)

    reader = DXFReader()
    registry = RecognizerRegistry()
    for r in [StraightBarRecognizer(), LBarRecognizer(), UBarRecognizer(), ClosedShapeRecognizer(),
              BranchRecognizer(), StructuralOutlineRecognizer(), DimensionRecognizer(), LeaderRecognizer()]:
        registry.register(r)

    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of or not drawing.capabilities.geometry:
            continue

        print(f"\nProcessing {filename}...")

        phase2 = reader.read_geometry(drawing.filepath, drawing.identity)
        canon_repo, _ = canonicalize(phase2, drawing.filepath)
        engine = SpatialQueryEngine.build(canon_repo)
        node_repo, _, _ = build_nodes(canon_repo, engine, filename)
        builder = TopologyBuilder(node_repo, canon_repo)
        graph, comp_repo, metrics6, _ = builder.build()

        cache = RecognitionCache()
        for comp in comp_repo.components.values():
            cache.set(comp.id, registry.evaluate(comp, graph))

        records = build_plausibility_records(comp_repo, cache)
        results = evaluate_plausibility(records)

        by_decision = {"accept": 0, "review": 0, "reject": 0}
        by_label_rejected = {}
        for r in results.values():
            by_decision[r.decision] += 1
            if r.decision == "reject":
                by_label_rejected[r.label] = by_label_rejected.get(r.label, 0) + 1

        out_dir = os.path.join("debug", "phase07_6", filename)
        payload = [
            {
                "component_uuid": str(cid),
                "label": r.label,
                "length": round(r.length, 2),
                "median_for_label": round(r.median_for_label, 2),
                "modified_z_score": round(r.modified_z_score, 3),
                "decision": r.decision,
                "evidence": [asdict(e) for e in r.evidence],
            }
            for cid, r in sorted(results.items(), key=lambda kv: str(kv[0]))
        ]
        _jdump(os.path.join(out_dir, "physical_plausibility.json"), payload)

        summary = {
            "Components Evaluated": len(results),
            "Accepted": by_decision["accept"],
            "Review": by_decision["review"],
            "Rejected": by_decision["reject"],
            "Rejected By Label": by_label_rejected,
        }
        _jdump(os.path.join(out_dir, "metrics.json"), summary)

        print("\nPlausibility Summary:")
        for k, v in summary.items():
            print(f"  {k:<24} : {v}")
        print(f"\n  Debug outputs written to {out_dir}")
        print("=" * 60)
        break


if __name__ == "__main__":
    main()
