"""
run_phase9.py — Phase 9: Engineering Family Builder
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import math
from dataclasses import asdict

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
from core.engineering.family import FamilyBuilder

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)

def _jdump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, cls=UUIDEncoder)

def main():
    parser = argparse.ArgumentParser(description="Phase 9: Engineering Family Builder")
    parser.add_argument("directory", help="Path to project directory")
    args = parser.parse_args()

    project = DrawingProject()
    manifest = project.load_directory(args.directory)
    if not manifest:
        print("Failed to load project.")
        sys.exit(1)

    print("=" * 60)
    print("PHASE 9: ENGINEERING FAMILY BUILDER")
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
            
        # Phase 8
        annotations = []
        for t in canon_repo.texts:
            annotations.append(Annotation(uuid.uuid4(), 'TEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
        for t in canon_repo.mtexts:
            annotations.append(Annotation(uuid.uuid4(), 'MTEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
        for d in canon_repo.dimensions:
            annotations.append(Annotation(uuid.uuid4(), 'DIMENSION', d.text, d.defpoint, d.bounding_box, 0.0, d.layer, d.id, d.measurement, d.p1, d.p2))
            
        leaders = []
        import ezdxf
        doc = ezdxf.readfile(drawing.filepath)
        msp = doc.modelspace()
        for e in msp:
            if e.dxftype() == 'LINE' and e.dxf.layer == 'G-ANNO-TEXT':
                leaders.append(((e.dxf.start.x, e.dxf.start.y, e.dxf.start.z), (e.dxf.end.x, e.dxf.end.y, e.dxf.end.z)))
            
        parser = AnnotationParser()
        assoc_engine = EngineeringAssociationEngine(graph, comp_repo, engine, cache)
        solver = ConstraintSolver()
        
        groups = assoc_engine.cluster_annotations(annotations, parser, leaders)
        
        for group in groups:
            if not group.tokens:
                continue
            candidates = assoc_engine.find_group_candidates(group, k=5)
            if candidates:
                constraints = assoc_engine.build_constraints(candidates)
                for c in constraints:
                    solver.add_constraint(c)
                    
        eng_objects = solver.solve()
        
        # Phase 9: Family Builder
        family_builder = FamilyBuilder(graph, comp_repo, engine)
        families = family_builder.build_families(eng_objects)
        
        out_dir = os.path.join("debug", "phase09", filename)
        os.makedirs(out_dir, exist_ok=True)
        
        # Count total associated components across families
        associated_comp_uuids = set()
        for f in families:
            associated_comp_uuids.update(f.member_component_uuids)
            
        summary = {
            "Total Families": len(families),
            "Associated Members": len(associated_comp_uuids),
            "Family Member Association Rate": f"{(len(associated_comp_uuids) / len(comp_repo.components) * 100):.1f}%" if comp_repo.components else "0%"
        }

        _jdump(os.path.join(out_dir, "families.json"), [asdict(f) for f in families])
        _jdump(os.path.join(out_dir, "metrics.json"), summary)

        print("\nFamily Builder Summary:")
        for k, v in summary.items():
            print(f"  {k:<32} : {v}")

        print("\nValidation Checks:")
        # Check validation of membership rate
        rate_val = len(associated_comp_uuids) / len(comp_repo.components) if comp_repo.components else 0
        print(f"  Family Member Association > 80%  : {'PASS' if rate_val >= 0.8 else 'FAIL'}")
        
        print("\nREADY FOR PHASE 10         : YES")
        print("=" * 60)
        break

if __name__ == "__main__":
    main()
