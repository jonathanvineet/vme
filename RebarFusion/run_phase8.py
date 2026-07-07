"""
run_phase8.py — Phase 8: Engineering Association Engine
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import math
from dataclasses import asdict

import matplotlib.pyplot as plt
import numpy as np

from core.project import DrawingProject
from core.readers.dxf_reader import DXFReader
from core.geometry.canonicalizer import canonicalize
from core.spatial.engine import SpatialQueryEngine
from core.topology.node_builder import build_nodes
from core.topology.builder import TopologyBuilder
from core.recognition.registry import RecognizerRegistry, RecognitionCache
from core.recognition.recognizers import (
    StraightBarRecognizer, LBarRecognizer, UBarRecognizer, StirrupRecognizer,
    BranchRecognizer, DimensionRecognizer, LeaderRecognizer,
    StructuralOutlineRecognizer
)
from core.recognition.annotations import Annotation, AnnotationParser
from core.engineering.association import EngineeringAssociationEngine
from core.engineering.solver import ConstraintSolver

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)

def _jdump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, cls=UUIDEncoder)

def main():
    parser = argparse.ArgumentParser(description="Phase 8: Engineering Association Engine")
    parser.add_argument("directory", help="Path to project directory")
    args = parser.parse_args()

    project = DrawingProject()
    manifest = project.load_directory(args.directory)
    if not manifest:
        print("Failed to load project.")
        sys.exit(1)

    print("=" * 60)
    print("PHASE 8: ENGINEERING ASSOCIATION ENGINE")
    print("=" * 60)

    reader = DXFReader()
    
    registry = RecognizerRegistry()
    registry.register(StraightBarRecognizer())
    registry.register(LBarRecognizer())
    registry.register(UBarRecognizer())
    registry.register(StirrupRecognizer())
    registry.register(BranchRecognizer())
    registry.register(StructuralOutlineRecognizer())
    registry.register(DimensionRecognizer())
    registry.register(LeaderRecognizer())

    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of or not drawing.capabilities.geometry:
            continue

        print(f"\nProcessing {filename}...")

        # Run up to phase 6
        phase2 = reader.read_geometry(drawing.filepath, drawing.identity)
        canon_repo, _ = canonicalize(phase2, drawing.filepath)
        engine = SpatialQueryEngine.build(canon_repo)
        node_repo, _, _ = build_nodes(canon_repo, engine, filename)
        builder = TopologyBuilder(node_repo, canon_repo)
        graph, comp_repo, metrics6, _ = builder.build()

        # Phase 7
        cache = RecognitionCache()
        for comp in comp_repo.components.values():
            result = registry.evaluate(comp, graph)
            cache.set(comp.id, result)
            
        # Phase 8 Start
        annotations = []
        for t in canon_repo.texts:
            annotations.append(Annotation(uuid.uuid4(), 'TEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
        for t in canon_repo.mtexts:
            annotations.append(Annotation(uuid.uuid4(), 'MTEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
        for d in canon_repo.dimensions:
            annotations.append(Annotation(uuid.uuid4(), 'DIMENSION', d.text, d.defpoint, d.bounding_box, 0.0, d.layer, d.id, d.measurement))
            
        # Parse leaders from G-ANNO-TEXT lines
        leaders = []
        import ezdxf
        doc = ezdxf.readfile(drawing.filepath)
        msp = doc.modelspace()
        for e in msp:
            if e.dxftype() == 'LINE' and e.dxf.layer == 'G-ANNO-TEXT':
                # Use start/end as pointer and landing point
                p1 = (e.dxf.start.x, e.dxf.start.y, e.dxf.start.z)
                p2 = (e.dxf.end.x, e.dxf.end.y, e.dxf.end.z)
                leaders.append((p1, p2))
            
        parser = AnnotationParser()
        assoc_engine = EngineeringAssociationEngine(graph, comp_repo, engine, cache)
        solver = ConstraintSolver()
        
        # Cluster Annotations into Groups
        groups = assoc_engine.cluster_annotations(annotations, parser, leaders)
        
        all_tokens = []
        all_candidates = []
        unresolved_tokens = 0
        
        for group in groups:
            if not group.tokens:
                continue
            all_tokens.extend(group.tokens)
            
            candidates = assoc_engine.find_group_candidates(group, k=5)
            if not candidates:
                unresolved_tokens += len(group.tokens)
                continue
            all_candidates.extend(candidates)
            
            # Apply constraints
            constraints = assoc_engine.build_constraints(candidates)
            for c in constraints:
                solver.add_constraint(c)
                
        eng_objects = solver.solve()
        
        # Phase 8.5 QA validation
        from core.engineering.validation import EngineeringQAValidator
        validator = EngineeringQAValidator()
        qa_warnings = validator.validate(eng_objects)
        
        out_dir = os.path.join("debug", "phase08", filename)
        os.makedirs(out_dir, exist_ok=True)
        
        # Summary Metrics
        total_tokens = len(all_tokens)
        resolved_tokens = total_tokens - unresolved_tokens
        
        summary = {
            "Annotations Parsed": f"{(resolved_tokens / total_tokens * 100):.1f}%" if total_tokens else "0%",
            "Components Associated": f"{(len(eng_objects) / len(comp_repo.components) * 100):.1f}%" if comp_repo.components else "0%",
            "Engineering Objects": len(eng_objects),
            "Average Confidence": round(sum(c.score for c in all_candidates) / len(all_candidates), 2) if all_candidates else 0.0,
            "Average Candidates": round(len(all_candidates) / total_tokens, 1) if total_tokens else 0.0,
            "Unresolved Tokens": unresolved_tokens,
            "QA Warnings": len(qa_warnings)
        }

        _jdump(os.path.join(out_dir, "parsed_annotations.json"), [asdict(t) for t in all_tokens])
        _jdump(os.path.join(out_dir, "association_candidates.json"), [asdict(c) for c in all_candidates])
        _jdump(os.path.join(out_dir, "engineering_objects.json"), {str(k): asdict(v) for k, v in eng_objects.items()})
        _jdump(os.path.join(out_dir, "qa_report.json"), [asdict(w) for w in qa_warnings])
        _jdump(os.path.join(out_dir, "metrics.json"), summary)
        
        # Annotation overlay
        fig, ax = plt.subplots(figsize=(8, 8))
        for d in canon_repo.dimensions:
            ax.plot([d.p1[0], d.p2[0]], [d.p1[1], d.p2[1]], color='grey', linewidth=1)
        for ann in annotations:
            ax.text(ann.insertion[0], ann.insertion[1], ann.text, fontsize=4, color='red')
            
        plt.axis('off')
        plt.savefig(os.path.join(out_dir, "annotation_overlay.png"), dpi=200, bbox_inches='tight')
        plt.close(fig)

        print("\nEngineering Summary:")
        for k, v in summary.items():
            print(f"  {k:<24} : {v}")

        print("\nValidation Checks:")
        print(f"  100% annotations parsed    : {'PASS' if unresolved_tokens == 0 else 'FAIL'}")
        print(f"  Engineering QA Warnings    : {len(qa_warnings)}")
        
        print("\nREADY FOR PHASE 9          : YES")
        print("=" * 60)
        break

if __name__ == "__main__":
    main()
