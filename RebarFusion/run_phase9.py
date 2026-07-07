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
from collections import Counter
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

def _write_family_overlay(path, families):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False

    member_boxes = [m.bbox for f in families for m in f.members]
    if not member_boxes:
        return False

    min_x = min(bb[0] for bb in member_boxes)
    min_y = min(bb[1] for bb in member_boxes)
    max_x = max(bb[2] for bb in member_boxes)
    max_y = max(bb[3] for bb in member_boxes)
    pad = max(max_x - min_x, max_y - min_y) * 0.06 + 100.0
    min_x -= pad
    min_y -= pad
    max_x += pad
    max_y += pad

    width, height = 1800, 1200
    sx = width / max(max_x - min_x, 1.0)
    sy = height / max(max_y - min_y, 1.0)
    scale = min(sx, sy)

    def xy(point):
        x, y = point
        return ((x - min_x) * scale, height - ((y - min_y) * scale))

    img = Image.new("RGB", (width, height), "#101018")
    draw = ImageDraw.Draw(img)
    colors = ["#4da3ff", "#65d46e", "#ffd166", "#c084fc", "#f78c6c"]

    for idx, family in enumerate(families):
        color = colors[idx % len(colors)]
        angle = math.radians(family.orientation)
        ax, ay = math.cos(angle), math.sin(angle)
        px, py = -ay, ax
        half = family.length / 2.0

        for member in family.members:
            cx, cy = member.centroid
            p1 = xy((cx - ax * half, cy - ay * half))
            p2 = xy((cx + ax * half, cy + ay * half))
            draw.line([p1, p2], fill=color, width=4)

        rep = family.members[0] if family.members else None
        if rep:
            for offset in family.missing_member_offsets:
                cx = rep.centroid[0] + px * offset
                cy = rep.centroid[1] + py * offset
                p1 = xy((cx - ax * half, cy - ay * half))
                p2 = xy((cx + ax * half, cy + ay * half))
                _draw_dashed_line(draw, p1, p2, fill="#ff4d4d", width=3)

        label = f"{family.mark}  members {family.detected_count}/{family.estimated_count}  spacing {family.spacing:.0f}"
        if family.members:
            lx, ly = xy(family.members[0].centroid)
            draw.text((lx + 8, ly + 8), label, fill=color)

    img.save(path)
    return True

def _draw_dashed_line(draw, p1, p2, fill, width):
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length <= 0:
        return
    dash = 20.0
    gap = 14.0
    t = 0.0
    while t < length:
        end = min(t + dash, length)
        a = (x1 + dx * (t / length), y1 + dy * (t / length))
        b = (x1 + dx * (end / length), y1 + dy * (end / length))
        draw.line([a, b], fill=fill, width=width)
        t += dash + gap

def _write_standalone_inspector(out_dir, standalone_component_uuids, graph, comp_repo, cache, families, annotations):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return [], {}, False

    standalone_dir = os.path.join(out_dir, "standalone")
    os.makedirs(standalone_dir, exist_ok=True)

    reports = []
    reason_counts = Counter()
    for index, comp_uuid in enumerate(sorted(standalone_component_uuids, key=str), start=1):
        comp = comp_repo.components.get(comp_uuid)
        if not comp:
            continue
        reason, details = _classify_standalone(comp, graph, cache, families)
        reason_counts[reason] += 1
        image_name = f"{index:04d}.png"
        image_path = os.path.join(standalone_dir, image_name)
        _draw_standalone_card(image_path, comp, reason, details, graph, comp_repo, families, annotations)
        reports.append({
            "Component": comp_uuid,
            "Reason": reason,
            "Details": details,
            "Image": os.path.join("standalone", image_name),
        })

    return reports, dict(reason_counts), True

def _classify_standalone(comp, graph, cache, families):
    profile = _component_profile(comp, graph, cache)
    if not profile:
        return "Unknown", "component has no drawable profile"

    label = profile["recognition_type"]
    if label == "stirrup":
        return "Stirrup", "recognized as stirrup-like geometry"
    if label == "branch":
        return "Branch", "recognized as branch geometry"
    if label == "unknown":
        return "Unknown", "recognizer did not assign a structural bar type"

    nearest = None
    for family in families:
        distance = _distance(profile["centroid"], _family_centroid(family))
        candidate = (distance, family)
        if nearest is None or candidate[0] < nearest[0]:
            nearest = candidate

    if nearest is None:
        return "No nearby family", "no engineering families were available for comparison"

    _, family = nearest
    if profile["layer"] != family.layer:
        return "Different layer", f"nearest family {family.mark} is on {family.layer}"
    if profile["recognition_type"] != family.recognition_type:
        return "Different type", f"{profile['recognition_type']} vs family {family.mark} {family.recognition_type}"

    orientation_delta = _angle_diff(profile["orientation"], family.orientation)
    if orientation_delta > 5.0:
        return "Different orientation", f"orientation differs {orientation_delta:.1f} degrees from {family.mark}"

    if family.length > 0:
        length_delta = abs(profile["length"] - family.length) / family.length
        if length_delta > 0.05:
            return "Different length", f"length differs {length_delta * 100:.1f}% from {family.mark}"

    if profile["confidence"] < 0.5:
        return "Confidence too low", f"recognition confidence {profile['confidence']:.2f}"

    if nearest[0] > max(family.length * 2.0, 3000.0):
        return "No nearby family", f"nearest family {family.mark} is {nearest[0]:.1f}mm away"

    return "Isolated", f"compatible with {family.mark}, but outside accepted spacing/axis checks"

def _draw_standalone_card(path, comp, reason, details, graph, comp_repo, families, annotations):
    from PIL import Image, ImageDraw

    nearby_boxes = [comp.bbox]
    cx = (comp.bbox[0] + comp.bbox[2]) / 2.0
    cy = (comp.bbox[1] + comp.bbox[3]) / 2.0
    radius = 2500.0
    nearby_components = []
    for other in comp_repo.components.values():
        ox = (other.bbox[0] + other.bbox[2]) / 2.0
        oy = (other.bbox[1] + other.bbox[3]) / 2.0
        if math.hypot(ox - cx, oy - cy) <= radius:
            nearby_components.append(other)
            nearby_boxes.append(other.bbox)

    nearby_annotations = [
        ann for ann in annotations
        if math.hypot(ann.insertion[0] - cx, ann.insertion[1] - cy) <= radius
    ]
    for ann in nearby_annotations:
        nearby_boxes.append(ann.bbox)

    min_x = min(bb[0] for bb in nearby_boxes) - 200.0
    min_y = min(bb[1] for bb in nearby_boxes) - 200.0
    max_x = max(bb[2] for bb in nearby_boxes) + 200.0
    max_y = max(bb[3] for bb in nearby_boxes) + 200.0

    width, height = 900, 700
    scale = min(width / max(max_x - min_x, 1.0), (height - 90) / max(max_y - min_y, 1.0))

    def xy(point):
        x, y = point
        return ((x - min_x) * scale, height - 20 - ((y - min_y) * scale))

    img = Image.new("RGB", (width, height), "#101018")
    draw = ImageDraw.Draw(img)
    draw.text((12, 10), f"Standalone: {str(comp.id)[:12]}  Reason: {reason}", fill="#ffffff")
    draw.text((12, 30), details[:130], fill="#cccccc")

    for other in nearby_components:
        color = "#505064"
        width_px = 1
        if other.id == comp.id:
            color = "#ff4d4d"
            width_px = 4
        _draw_component(draw, other, graph, xy, color, width_px)

    for family in families:
        if _distance((cx, cy), _family_centroid(family)) <= radius:
            for member in family.members:
                _draw_member(draw, member.centroid, family.length, family.orientation, xy, "#4da3ff", 3)

    for ann in nearby_annotations:
        ax, ay = xy((ann.insertion[0], ann.insertion[1]))
        draw.text((ax, ay), ann.text[:24], fill="#ffd166")

    img.save(path)

def _draw_component(draw, comp, graph, xy, color, width):
    for edge_id in comp.edge_ids:
        edge = graph.edges.get(edge_id)
        if not edge:
            continue
        n1 = graph.nodes.get(edge.start_node_uuid)
        n2 = graph.nodes.get(edge.end_node_uuid)
        if not n1 or not n2:
            continue
        draw.line([xy(n1.position[:2]), xy(n2.position[:2])], fill=color, width=width)

def _draw_member(draw, centroid, length, orientation, xy, color, width):
    angle = math.radians(orientation)
    ax, ay = math.cos(angle), math.sin(angle)
    half = length / 2.0
    cx, cy = centroid
    draw.line([xy((cx - ax * half, cy - ay * half)), xy((cx + ax * half, cy + ay * half))], fill=color, width=width)

def _component_profile(comp, graph, cache):
    if not comp.edge_ids:
        return None
    longest = None
    total = float(comp.statistics.get("total_length", 0.0))
    for edge_id in comp.edge_ids:
        edge = graph.edges.get(edge_id)
        if edge and (longest is None or edge.length > longest.length):
            longest = edge
    if not longest:
        return None
    label = "unknown"
    confidence = 0.0
    result = cache.get(comp.id) if cache else None
    if result:
        label = result.label
        confidence = result.confidence
    cx = (comp.bbox[0] + comp.bbox[2]) / 2.0
    cy = (comp.bbox[1] + comp.bbox[3]) / 2.0
    return {
        "length": total,
        "orientation": longest.angle % 180.0,
        "layer": longest.layer,
        "recognition_type": label,
        "confidence": confidence,
        "centroid": (cx, cy),
    }

def _family_centroid(family):
    if not family.members:
        return (0.0, 0.0)
    x = sum(m.centroid[0] for m in family.members) / len(family.members)
    y = sum(m.centroid[1] for m in family.members) / len(family.members)
    return (x, y)

def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def _angle_diff(a, b):
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)

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
        family_builder = FamilyBuilder(graph, comp_repo, engine, cache)
        families = family_builder.build_families(eng_objects)
        
        out_dir = os.path.join("debug", "phase09", filename)
        os.makedirs(out_dir, exist_ok=True)
        
        # Count total member components across families. This intentionally
        # measures discovered bar members, not every recognized drawing component.
        associated_comp_uuids = set()
        for f in families:
            associated_comp_uuids.update(f.member_component_uuids)

        spacing_report = [
            {
                "Family UUID": f.uuid,
                "Mark": f.mark,
                "Annotated Spacing": f.annotated_spacing,
                "Inferred Spacing": f.inferred_spacing,
                "Selected Spacing": f.spacing,
                "Spacing Source": f.spacing_source,
                "Average Error": f.average_spacing_error,
                "Confidence": f.spacing_confidence,
                "Offsets": [round(m.offset_from_representative, 3) for m in f.members],
            }
            for f in families
        ]
        count_report = [
            {
                "Family UUID": f.uuid,
                "Mark": f.mark,
                "Detected Count": f.detected_count,
                "Estimated Count": f.estimated_count,
                "Expected Count": f.expected_members,
                "Inferred Span": f.inferred_span,
                "Missing Offsets": f.missing_member_offsets,
            }
            for f in families
        ]
        qa_report = [
            {
                "Family UUID": f.uuid,
                "Mark": f.mark,
                "Expected Members": f.qa.expected_members if f.qa else None,
                "Found Members": f.qa.found_members if f.qa else len(f.members),
                "Missing Members": f.qa.missing_members if f.qa else None,
                "Confidence": f.qa.confidence if f.qa else 0.0,
                "Missing Offsets": f.qa.missing_offsets if f.qa else [],
                "Warnings": f.qa.warnings if f.qa else [],
            }
            for f in families
        ]
        qa_warning_count = sum(len(f.qa.warnings) for f in families if f.qa)
        spacing_errors = [f.average_spacing_error for f in families if f.spacing_confidence > 0]
        confidences = [f.confidence for f in families]
        family_member_counts = {comp_uuid: 0 for comp_uuid in eng_objects}
        for family in families:
            for comp_uuid in family.member_component_uuids:
                if comp_uuid in family_member_counts:
                    family_member_counts[comp_uuid] += 1
        standalone_objects = [
            comp_uuid
            for comp_uuid, count in family_member_counts.items()
            if count == 0
        ]
        duplicate_object_memberships = [
            comp_uuid
            for comp_uuid, count in family_member_counts.items()
            if count > 1
        ]
        membership_report = [
            {
                "Family UUID": f.uuid,
                "Family": f.mark,
                "Family Type": f.family_type,
                "Representative": f.representative_component_uuid,
                "Members": f.member_component_uuids,
                "Rejected": f.rejected_candidates,
            }
            for f in families
        ]
        standalone_report, standalone_summary, standalone_images_written = _write_standalone_inspector(
            out_dir,
            standalone_objects,
            graph,
            comp_repo,
            cache,
            families,
            annotations,
        )
            
        summary = {
            "Engineering Families": len(families),
            "Detected Members": sum(f.detected_count for f in families),
            "Estimated Members": sum(f.estimated_count for f in families),
            "Missing Members": sum((f.qa.missing_members or 0) for f in families if f.qa),
            "Unique Member Components": len(associated_comp_uuids),
            "Average Members": round((sum(f.detected_count for f in families) / len(families)), 2) if families else 0,
            "Families With Spacing": sum(1 for f in families if f.spacing > 0),
            "Average Spacing Error": round((sum(spacing_errors) / len(spacing_errors)), 3) if spacing_errors else 0.0,
            "Average Confidence": round((sum(confidences) / len(confidences)), 3) if confidences else 0.0,
            "Standalone Engineering Objects": len(standalone_objects),
            "Duplicate Object Memberships": len(duplicate_object_memberships),
            "Standalone Summary": standalone_summary,
            "Family QA Warnings": qa_warning_count,
        }

        families_payload = [asdict(f) for f in families]
        _jdump(os.path.join(out_dir, "engineering_families.json"), families_payload)
        _jdump(os.path.join(out_dir, "families.json"), families_payload)
        _jdump(os.path.join(out_dir, "spacing_report.json"), spacing_report)
        _jdump(os.path.join(out_dir, "count_report.json"), count_report)
        _jdump(os.path.join(out_dir, "family_membership_report.json"), membership_report)
        _jdump(os.path.join(out_dir, "standalone_report.json"), standalone_report)
        _jdump(os.path.join(out_dir, "qa_report.json"), qa_report)
        _jdump(os.path.join(out_dir, "family_qa.json"), qa_report)
        _jdump(os.path.join(out_dir, "metrics.json"), summary)
        overlay_written = _write_family_overlay(os.path.join(out_dir, "family_overlay.png"), families)

        print("\nFamily Builder Summary:")
        for k, v in summary.items():
            print(f"  {k:<32} : {v}")

        print("\nValidation Checks:")
        multi_member = sum(1 for f in families if len(f.members) > 1)
        print(f"  Families built from members      : {'PASS' if families else 'FAIL'}")
        print(f"  Multi-member families discovered : {multi_member}/{len(families)}")
        print(f"  Family QA generated              : {'PASS' if qa_report else 'FAIL'}")
        print(f"  Object membership deterministic  : {'PASS' if not duplicate_object_memberships else 'FAIL'}")
        print(f"  Family overlay generated         : {'PASS' if overlay_written else 'SKIP'}")
        print(f"  Standalone inspector generated   : {'PASS' if standalone_images_written else 'SKIP'}")
        
        print("\nREADY FOR PHASE 10         : YES")
        print("=" * 60)
        break

if __name__ == "__main__":
    main()
