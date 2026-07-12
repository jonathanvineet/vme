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
    StraightBarRecognizer, LBarRecognizer, UBarRecognizer, ClosedShapeRecognizer,
    BranchRecognizer, DimensionRecognizer, LeaderRecognizer,
    StructuralOutlineRecognizer
)
from core.recognition.annotations import Annotation, AnnotationParser
from core.recognition.leaders import reconstruct_leaders
from core.recognition.plausibility import evaluate_plausibility
from core.engineering.association import EngineeringAssociationEngine
from core.engineering.solver import ConstraintSolver
from core.engineering.family import FamilyBuilder
from core.engineering.spacing import measure_family_spacing, compute_family_statistics
from core.engineering.confidence import build_confidence_breakdown

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

def _draw_spacing_gallery(path, family, measurements):
    """Phase 9.3: one card per family with measurable spacing — members
    along the perpendicular axis, each gap labeled with its measured
    distance, outlier gaps drawn in red instead of green."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False
    if not family.members:
        return False

    angle = math.radians(family.orientation)
    ax, ay = math.cos(angle), math.sin(angle)
    px, py = -ay, ax
    half = family.length / 2.0

    members = sorted(family.members, key=lambda m: m.offset_from_representative)
    boxes = []
    for m in members:
        cx, cy = m.centroid
        boxes.append((cx - ax * half, cy - ay * half))
        boxes.append((cx + ax * half, cy + ay * half))

    min_x = min(b[0] for b in boxes) - 150.0
    min_y = min(b[1] for b in boxes) - 150.0
    max_x = max(b[0] for b in boxes) + 150.0
    max_y = max(b[1] for b in boxes) + 150.0

    width, height = 1000, 700
    scale = min(width / max(max_x - min_x, 1.0), (height - 60) / max(max_y - min_y, 1.0))

    def xy(point):
        x, y = point
        return ((x - min_x) * scale, height - 60 - ((y - min_y) * scale))

    img = Image.new("RGB", (width, height), "#101018")
    draw = ImageDraw.Draw(img)

    for m in members:
        cx, cy = m.centroid
        draw.line([xy((cx - ax * half, cy - ay * half)), xy((cx + ax * half, cy + ay * half))], fill="#4da3ff", width=4)

    by_pair = {(m.member_a, m.member_b): m for m in measurements}
    for a, b in zip(members, members[1:]):
        meas = by_pair.get((a.component_uuid, b.component_uuid))
        color = "#ff4d4d" if (meas and meas.is_outlier) else "#65d46e"
        mid = ((a.centroid[0] + b.centroid[0]) / 2.0, (a.centroid[1] + b.centroid[1]) / 2.0)
        draw.line([xy(a.centroid), xy(b.centroid)], fill=color, width=2)
        label = f"{meas.measured_spacing:.0f}mm" if meas else "?"
        if meas and meas.is_outlier:
            label += f" OUTLIER (residual {meas.residual:+.0f}mm)"
        lx, ly = xy(mid)
        draw.text((lx + 6, ly - 14), label, fill=color)

    draw.text((10, height - 40), f"Family {family.mark}  ref spacing {family.spacing:.0f}mm  members {len(members)}", fill="#e5e5e5")
    img.save(path)
    return True


def _draw_confidence_card(path, breakdown):
    """Phase 9.4: one glance card showing every confidence dimension as a
    labeled bar, so a low overall score is immediately traceable to which
    stage caused it."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False

    rows = [
        ("Geometry", breakdown.geometry),
        ("Recognition", breakdown.recognition),
        ("Plausibility", breakdown.plausibility),
        ("Annotation", breakdown.annotation),
        ("Association", breakdown.association),
        ("Spacing", breakdown.spacing),
        ("Family", breakdown.family_consistency),
        ("Overall", breakdown.overall),
    ]

    width, height = 640, 60 + 40 * len(rows)
    img = Image.new("RGB", (width, height), "#101018")
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), f"Family {breakdown.mark}  (weakest: {breakdown.weakest_dimension})", fill="#e5e5e5")

    bar_x0 = 140
    bar_max_w = width - bar_x0 - 60
    for i, (label, score) in enumerate(rows):
        y = 50 + i * 40
        color = "#65d46e" if score >= 0.8 else ("#ffd166" if score >= 0.5 else "#ff4d4d")
        if label == "Overall":
            color = "#4da3ff"
        draw.text((10, y), label, fill="#e5e5e5")
        draw.rectangle([bar_x0, y, bar_x0 + bar_max_w, y + 22], outline="#3a3a4a")
        draw.rectangle([bar_x0, y, bar_x0 + int(bar_max_w * max(0.0, min(1.0, score))), y + 22], fill=color)
        draw.text((bar_x0 + bar_max_w + 8, y), f"{score:.2f}", fill="#e5e5e5")

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

# Maps a fine-grained rejection reason to the gallery bucket requested for
# Phase 9.2 (family_rejected / orientation_rejected / length_rejected /
# isolated), so images are organized by *why* rather than dumped flat.
_GALLERY_BUCKETS = {
    "Different type": "family_rejected",
    "Different layer": "family_rejected",
    "No nearby family": "family_rejected",
    "Different orientation": "orientation_rejected",
    "Different length": "length_rejected",
    "Isolated": "isolated",
    "Confidence too low": "isolated",
    "Stirrup": "isolated",
    "Branch": "isolated",
    "Unknown": "isolated",
}


def _write_standalone_inspector(out_dir, standalone_component_uuids, graph, comp_repo, cache, families, annotations):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return [], {}, [], True

    standalone_dir = os.path.join(out_dir, "standalone")
    os.makedirs(standalone_dir, exist_ok=True)

    reports = []
    provenance = []
    reason_counts = Counter()
    for index, comp_uuid in enumerate(sorted(standalone_component_uuids, key=str), start=1):
        comp = comp_repo.components.get(comp_uuid)
        if not comp:
            continue
        reason, details, evidence = _classify_standalone(comp, graph, cache, families)
        reason_counts[reason] += 1

        bucket = _GALLERY_BUCKETS.get(reason, "isolated")
        bucket_dir = os.path.join(standalone_dir, bucket)
        os.makedirs(bucket_dir, exist_ok=True)
        image_name = f"{index:04d}.png"
        image_path = os.path.join(bucket_dir, image_name)
        _draw_standalone_card(image_path, comp, reason, details, graph, comp_repo, families, annotations)
        image_rel = os.path.join("standalone", bucket, image_name)

        reports.append({
            "Component": comp_uuid,
            "Reason": reason,
            "Details": details,
            "Image": image_rel,
        })
        provenance.append({
            "component_uuid": str(comp_uuid),
            "reason": reason,
            "details": details,
            "image": image_rel,
            **evidence,
        })

    return reports, dict(reason_counts), provenance, True

def _classify_standalone(comp, graph, cache, families):
    """
    Returns (reason, details, evidence). `evidence` carries the full numeric
    comparison against the nearest family (Phase 9.2 standalone provenance
    audit) rather than only a formatted text summary, so every standalone
    object's rejection can be inspected/aggregated precisely instead of
    re-parsed from prose.
    """
    profile = _component_profile(comp, graph, cache)
    if not profile:
        return "Unknown", "component has no drawable profile", {"nearest_family": None}

    label = profile["recognition_type"]
    base_evidence = {
        "recognition_type": label,
        "layer": profile["layer"],
        "length": round(profile["length"], 2),
        "orientation": round(profile["orientation"], 2),
        "confidence": round(profile["confidence"], 3),
    }
    if label == "stirrup":
        return "Stirrup", "recognized as stirrup-like geometry", {**base_evidence, "nearest_family": None}
    if label == "branch":
        return "Branch", "recognized as branch geometry", {**base_evidence, "nearest_family": None}
    if label == "unknown":
        return "Unknown", "recognizer did not assign a structural bar type", {**base_evidence, "nearest_family": None}

    nearest = None
    for family in families:
        distance = _distance(profile["centroid"], _family_centroid(family))
        candidate = (distance, family)
        if nearest is None or candidate[0] < nearest[0]:
            nearest = candidate

    if nearest is None:
        return "No nearby family", "no engineering families were available for comparison", \
            {**base_evidence, "nearest_family": None}

    distance, family = nearest
    orientation_delta = _angle_diff(profile["orientation"], family.orientation)
    length_delta_pct = (abs(profile["length"] - family.length) / family.length * 100.0) if family.length > 0 else None
    nearest_info = {
        "nearest_family_uuid": str(family.uuid),
        "nearest_family_mark": family.mark,
        "distance_mm": round(distance, 1),
        "family_layer": family.layer,
        "family_recognition_type": family.recognition_type,
        "family_length": round(family.length, 2),
        "orientation_delta_deg": round(orientation_delta, 2),
        "length_delta_pct": round(length_delta_pct, 1) if length_delta_pct is not None else None,
    }
    evidence = {**base_evidence, "nearest_family": nearest_info}

    if profile["layer"] != family.layer:
        return "Different layer", f"nearest family {family.mark} is on {family.layer}", evidence
    if profile["recognition_type"] != family.recognition_type:
        return "Different type", f"{profile['recognition_type']} vs family {family.mark} {family.recognition_type}", evidence

    if orientation_delta > 5.0:
        return "Different orientation", f"orientation differs {orientation_delta:.1f} degrees from {family.mark}", evidence

    if length_delta_pct is not None and length_delta_pct > 5.0:
        return "Different length", f"length differs {length_delta_pct:.1f}% from {family.mark}", evidence

    if profile["confidence"] < 0.5:
        return "Confidence too low", f"recognition confidence {profile['confidence']:.2f}", evidence

    if distance > max(family.length * 2.0, 3000.0):
        return "No nearby family", f"nearest family {family.mark} is {distance:.1f}mm away", evidence

    return "Isolated", f"compatible with {family.mark}, but outside accepted spacing/axis checks", evidence

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
    registry.register(ClosedShapeRecognizer())
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

        # Phase 7.6: Physical Plausibility (see core/recognition/plausibility.py)
        plausibility_records = {
            comp.id: {"label": cache.get(comp.id).label, "length": float(comp.statistics.get("total_length", 0.0))}
            for comp in comp_repo.components.values()
            if cache.get(comp.id) and cache.get(comp.id).label in
            {"straight_bar", "l_bar", "u_bar", "stirrup", "branch"}
        }
        plausibility = evaluate_plausibility(plausibility_records)

        # Phase 8
        annotations = []
        for t in canon_repo.texts:
            annotations.append(Annotation(uuid.uuid4(), 'TEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
        for t in canon_repo.mtexts:
            annotations.append(Annotation(uuid.uuid4(), 'MTEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
        for d in canon_repo.dimensions:
            annotations.append(Annotation(uuid.uuid4(), 'DIMENSION', d.text, d.defpoint, d.bounding_box, 0.0, d.layer, d.id, d.measurement, d.p1, d.p2))
            
        leader_repo = reconstruct_leaders(graph, comp_repo, layer="G-ANNO-TEXT")
        leaders = list(leader_repo.leaders.values())

        parser = AnnotationParser()
        assoc_engine = EngineeringAssociationEngine(graph, comp_repo, engine, cache, plausibility=plausibility)
        solver = ConstraintSolver()
        
        groups = assoc_engine.cluster_annotations(annotations, parser, leaders)

        all_candidates = []
        for group in groups:
            if not group.tokens:
                continue
            candidates = assoc_engine.find_group_candidates(group, k=5)
            if candidates:
                all_candidates.extend(candidates)
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

        # Phase 9.3: Spacing Validation Audit — per-gap provenance and
        # per-family statistics (RMSE/bias/std dev), not one pooled average.
        all_spacing_measurements = []
        family_spacing_stats = []
        family_measurements_by_uuid = {}
        for f in families:
            measurements = measure_family_spacing(f)
            stats = compute_family_statistics(f, measurements)
            all_spacing_measurements.extend(measurements)
            family_measurements_by_uuid[f.uuid] = measurements
            if stats:
                family_spacing_stats.append(stats)
        spacing_outliers = [m for m in all_spacing_measurements if m.is_outlier]

        spacing_gallery_dir = os.path.join(out_dir, "spacing")
        os.makedirs(spacing_gallery_dir, exist_ok=True)
        for f in families:
            measurements = family_measurements_by_uuid.get(f.uuid, [])
            if measurements:
                _draw_spacing_gallery(os.path.join(spacing_gallery_dir, f"{f.mark}_{str(f.uuid)[:8]}.png"), f, measurements)

        # Phase 9.4: Confidence Decomposition (see core/engineering/confidence.py)
        confidence_dir = os.path.join("debug", "phase09_4", filename)
        confidence_gallery_dir = os.path.join(confidence_dir, "family_confidence_gallery")
        os.makedirs(confidence_gallery_dir, exist_ok=True)
        confidence_breakdowns = [
            build_confidence_breakdown(f, cache, plausibility, all_candidates) for f in families
        ]
        for cb in confidence_breakdowns:
            _draw_confidence_card(
                os.path.join(confidence_gallery_dir, f"{cb.mark}_{str(cb.family_uuid)[:8]}.png"), cb
            )
        low_confidence_objects = [
            {
                "family_uuid": str(cb.family_uuid),
                "mark": cb.mark,
                "overall": cb.overall,
                "weakest_dimension": cb.weakest_dimension,
                "weakest_score": getattr(cb, cb.weakest_dimension),
                "evidence": [asdict(e) for e in cb.evidence],
            }
            for cb in confidence_breakdowns if cb.overall < 0.70
        ]
        confidence_histogram = Counter()
        for cb in confidence_breakdowns:
            bucket = round(cb.overall, 1)
            confidence_histogram[bucket] += 1

        _jdump(os.path.join(confidence_dir, "confidence_breakdown.json"), [asdict(cb) for cb in confidence_breakdowns])
        _jdump(os.path.join(confidence_dir, "confidence_summary.json"), {
            "families_evaluated": len(confidence_breakdowns),
            "mean_overall": round(sum(cb.overall for cb in confidence_breakdowns) / len(confidence_breakdowns), 3) if confidence_breakdowns else 0.0,
            "low_confidence_count": len(low_confidence_objects),
            "weakest_dimension_counts": dict(Counter(cb.weakest_dimension for cb in confidence_breakdowns)),
        })
        _jdump(os.path.join(confidence_dir, "confidence_histogram.json"), dict(sorted(confidence_histogram.items())))
        _jdump(os.path.join(confidence_dir, "low_confidence_objects.json"), low_confidence_objects)

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
        standalone_report, standalone_summary, standalone_provenance, standalone_images_written = _write_standalone_inspector(
            out_dir,
            standalone_objects,
            graph,
            comp_repo,
            cache,
            families,
            annotations,
        )

        # Informational only: which marks are claimed by more than one family.
        # This is expected in general (the same mark can legitimately label
        # multiple separate physical bar groups), but it's worth surfacing
        # for review rather than staying silent, since it can also indicate
        # family fragmentation (a group that should be one family split into
        # several) or a spurious mark association upstream in Phase 8.
        mark_to_families: Dict[str, List[str]] = {}
        for f in families:
            mark_to_families.setdefault(f.mark, []).append(str(f.uuid))
        cross_family_marks = {
            mark: fam_uuids for mark, fam_uuids in mark_to_families.items() if len(fam_uuids) > 1
        }

        summary = {
            "Engineering Families": len(families),
            "Detected Members": sum(f.detected_count for f in families),
            "Estimated Members": sum(f.estimated_count for f in families),
            "Missing Members": sum((f.qa.missing_members or 0) for f in families if f.qa),
            "Unique Member Components": len(associated_comp_uuids),
            "Average Members": round((sum(f.detected_count for f in families) / len(families)), 2) if families else 0,
            "Families With Spacing": sum(1 for f in families if f.spacing > 0),
            "Average Spacing Error (pooled, legacy metric)": round((sum(spacing_errors) / len(spacing_errors)), 3) if spacing_errors else 0.0,
            "Per-Family Spacing RMSE (see spacing_statistics.json)": {
                s.mark: {"rmse": s.rmse, "bias": s.bias, "std_dev": s.std_dev, "gaps": s.gap_count, "outliers": s.outlier_count}
                for s in family_spacing_stats
            },
            "Spacing Outliers": len(spacing_outliers),
            "Average Confidence (legacy pooled metric)": round((sum(confidences) / len(confidences)), 3) if confidences else 0.0,
            "Confidence Breakdown (see confidence_breakdown.json)": {
                cb.mark: {
                    "geometry": cb.geometry, "recognition": cb.recognition, "plausibility": cb.plausibility,
                    "annotation": cb.annotation, "association": cb.association, "spacing": cb.spacing,
                    "family": cb.family_consistency, "overall": cb.overall, "weakest": cb.weakest_dimension,
                }
                for cb in confidence_breakdowns
            },
            "Low Confidence Families (<0.70)": len(low_confidence_objects),
            "Standalone Engineering Objects": len(standalone_objects),
            "Duplicate Object Memberships": len(duplicate_object_memberships),
            "Standalone Summary": standalone_summary,
            "Family QA Warnings": qa_warning_count,
            "Cross-Family Shared Marks (info)": cross_family_marks,
            "Plausibility Rejected (excluded from candidacy)": sum(1 for p in plausibility.values() if p.decision == "reject"),
            "Plausibility Review (kept, flagged)": sum(1 for p in plausibility.values() if p.decision == "review"),
        }

        # Spacing histogram: measured-gap distribution across every family,
        # 50mm bins, for a quick shape check independent of per-family stats.
        spacing_histogram = Counter()
        for m in all_spacing_measurements:
            bucket = int(m.measured_spacing // 50) * 50
            spacing_histogram[bucket] += 1

        families_payload = [asdict(f) for f in families]
        _jdump(os.path.join(out_dir, "engineering_families.json"), families_payload)
        _jdump(os.path.join(out_dir, "families.json"), families_payload)
        _jdump(os.path.join(out_dir, "spacing_report.json"), spacing_report)
        _jdump(os.path.join(out_dir, "spacing_measurements.json"), [asdict(m) for m in all_spacing_measurements])
        _jdump(os.path.join(out_dir, "spacing_statistics.json"), [asdict(s) for s in family_spacing_stats])
        _jdump(os.path.join(out_dir, "spacing_outliers.json"), [asdict(m) for m in spacing_outliers])
        _jdump(os.path.join(out_dir, "spacing_histogram.json"), dict(sorted(spacing_histogram.items())))
        _jdump(os.path.join(out_dir, "count_report.json"), count_report)
        _jdump(os.path.join(out_dir, "family_membership_report.json"), membership_report)
        _jdump(os.path.join(out_dir, "standalone_report.json"), standalone_report)
        _jdump(os.path.join(out_dir, "standalone_provenance.json"), standalone_provenance)
        _jdump(os.path.join(out_dir, "qa_report.json"), qa_report)
        _jdump(os.path.join(out_dir, "family_qa.json"), qa_report)
        _jdump(os.path.join(out_dir, "cross_family_marks.json"), cross_family_marks)
        _jdump(os.path.join(out_dir, "metrics.json"), summary)
        overlay_written = _write_family_overlay(os.path.join(out_dir, "family_overlay.png"), families)

        print("\nFamily Builder Summary:")
        for k, v in summary.items():
            print(f"  {k:<32} : {v}")

        print("\nValidation Checks:")
        multi_member = sum(1 for f in families if len(f.members) > 1)
        families_built_ok = bool(families)
        qa_generated_ok = bool(qa_report)
        membership_deterministic_ok = not duplicate_object_memberships
        print(f"  Families built from members      : {'PASS' if families_built_ok else 'FAIL'}")
        print(f"  Multi-member families discovered : {multi_member}/{len(families)}")
        print(f"  Family QA generated              : {'PASS' if qa_generated_ok else 'FAIL'}")
        print(f"  Object membership deterministic  : {'PASS' if membership_deterministic_ok else 'FAIL'}")
        print(f"  Family overlay generated         : {'PASS' if overlay_written else 'SKIP'}")
        print(f"  Standalone inspector generated   : {'PASS' if standalone_images_written else 'SKIP'}")

        ready = families_built_ok and qa_generated_ok and membership_deterministic_ok
        print(f"\nREADY FOR PHASE 10         : {'YES' if ready else 'NO'}")
        print("=" * 60)
        break

if __name__ == "__main__":
    main()
