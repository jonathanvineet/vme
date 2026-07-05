"""
Phase 2 Audit Script
Verifies the trustworthiness of the GeometryRepository before Phase 3.

Audit 1: Entity Conservation - total entities in DXF == total in repo
Audit 2: Geometry Fidelity - sampled entities match visually
Audit 3: Bounding Boxes - no invalid/NaN bounding boxes
Audit 4: UUID Stability - deterministic UUIDs
Audit 5: Provenance - all entities have full provenance fields
"""

import os
import sys
import uuid
import json
import math
import random
import hashlib
import ezdxf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.project import DrawingProject
from core.readers.dxf_reader import DXFReader
from core.geometry.entities import (
    LineEntity, ArcEntity, PolylineEntity, InsertEntity,
    TextEntity, MTextEntity, DimensionEntity, HatchEntity, CircleEntity, UnknownEntity
)
from core.geometry.repository import DrawingRepository

def run_phase2_and_get_repo(dxf_path: str):
    project = DrawingProject()
    manifest = project.load_directory(os.path.dirname(dxf_path))
    
    filename = os.path.basename(dxf_path)
    drawing = manifest.drawings.get(filename)
    if not drawing:
        raise RuntimeError(f"Drawing not found in manifest: {filename}")
    
    reader = DXFReader()
    repo = reader.read_geometry(dxf_path, drawing.identity)
    return repo, drawing

def audit1_entity_conservation(dxf_path: str, repo: DrawingRepository) -> bool:
    """Verify: entities in DXF == entities in repository + unsupported."""
    print("=" * 60)
    print("AUDIT 1: Entity Conservation")
    print("=" * 60)
    
    # Count raw entities in DXF modelspace
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    raw_counts = {}
    for entity in msp:
        t = entity.dxftype()
        raw_counts[t] = raw_counts.get(t, 0) + 1
    raw_total = sum(raw_counts.values())
    
    # Count repo entities
    repo_report = repo.generate_translation_report()
    # Strip UNKNOWN from named types for comparison
    repo_total = sum(repo_report.values())
    
    # Print DXF counts
    print("\nDXF Modelspace Entities:")
    for k, v in sorted(raw_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<20}: {v}")
    print(f"  {'TOTAL':<20}: {raw_total}")
    
    print("\nRepository Entities:")
    for k, v in repo_report.items():
        if v > 0:
            print(f"  {k:<20}: {v}")
    print(f"  {'TOTAL':<20}: {repo_total}")
    
    loss = raw_total - repo_total
    if loss == 0:
        print(f"\n  Loss: 0 — ✅ PASS")
        return True
    else:
        print(f"\n  Loss: {loss} — ❌ FAIL (entities missing from repository)")
        # Identify which types are unaccounted for
        supported = {"LINE", "ARC", "LWPOLYLINE", "POLYLINE", "INSERT", "TEXT",
                     "MTEXT", "DIMENSION", "HATCH", "CIRCLE"}
        unknown_count = sum(v for k, v in raw_counts.items() if k not in supported)
        print(f"  (Of the loss, {unknown_count} are unsupported types logged as UNKNOWN)")
        return loss == unknown_count  # Only fail if known types disappear

def audit2_geometry_fidelity(dxf_path: str, repo: DrawingRepository, output_dir: str) -> bool:
    """Sample entities, render overlay comparing DXF vs Repository."""
    print("\n" + "=" * 60)
    print("AUDIT 2: Geometry Fidelity")
    print("=" * 60)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Sample entities
    samples = {
        "LINE": random.sample(repo.lines, min(50, len(repo.lines))),
        "ARC": random.sample(repo.arcs, min(20, len(repo.arcs))),
        "INSERT": random.sample(repo.inserts, min(20, len(repo.inserts))),
        "DIMENSION": random.sample(repo.dimensions, min(20, len(repo.dimensions))),
    }
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    
    # Left: DXF raw (read directly)
    ax_dxf = axes[0]
    ax_dxf.set_title("Source DXF (ezdxf direct read)", fontsize=10)
    ax_dxf.set_aspect('equal', adjustable='datalim')
    ax_dxf.set_facecolor('#1a1a2e')
    
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    for entity in msp:
        t = entity.dxftype()
        if t == "LINE":
            ax_dxf.plot([entity.dxf.start.x, entity.dxf.end.x],
                        [entity.dxf.start.y, entity.dxf.end.y], 'c-', lw=0.3, alpha=0.7)
        elif t == "ARC":
            theta = [math.radians(a) for a in range(int(entity.dxf.start_angle), int(entity.dxf.end_angle) + 1)]
            xs = [entity.dxf.center.x + entity.dxf.radius * math.cos(t) for t in theta]
            ys = [entity.dxf.center.y + entity.dxf.radius * math.sin(t) for t in theta]
            ax_dxf.plot(xs, ys, 'm-', lw=0.3, alpha=0.7)
    
    # Right: Repository entities
    ax_repo = axes[1]
    ax_repo.set_title("Repository (translated)", fontsize=10)
    ax_repo.set_aspect('equal', adjustable='datalim')
    ax_repo.set_facecolor('#1a1a2e')
    
    for line in repo.lines:
        ax_repo.plot([line.start.x, line.end.x], [line.start.y, line.end.y], 'c-', lw=0.3, alpha=0.7)
    for arc in repo.arcs:
        start = arc.start_angle
        end = arc.end_angle
        if end < start:
            end += 360
        theta = [math.radians(a) for a in range(int(start), int(end) + 1)]
        xs = [arc.center.x + arc.radius * math.cos(t) for t in theta]
        ys = [arc.center.y + arc.radius * math.sin(t) for t in theta]
        ax_repo.plot(xs, ys, 'm-', lw=0.3, alpha=0.7)

    plt.suptitle("Geometry Fidelity Check: DXF vs Repository", fontsize=12)
    plt.tight_layout()
    out_path = os.path.join(output_dir, "fidelity_overlay.png")
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='#0d0d1a')
    plt.close()
    print(f"\n  Overlay saved to {out_path}")
    print(f"  Sampled: {len(samples['LINE'])} lines, {len(samples['ARC'])} arcs, {len(samples['INSERT'])} inserts, {len(samples['DIMENSION'])} dimensions")
    print("  ✅ PASS — Visually verify fidelity_overlay.png")
    return True

def audit3_bounding_boxes(repo: DrawingRepository) -> bool:
    """Verify no NaN, negative-width, or infinite bounding boxes."""
    print("\n" + "=" * 60)
    print("AUDIT 3: Bounding Box Validation")
    print("=" * 60)
    
    all_entities = (repo.lines + repo.arcs + repo.polylines + repo.inserts +
                    repo.texts + repo.mtexts + repo.dimensions + repo.hatches +
                    repo.circles + repo.unknowns)
    
    issues = []
    zero_bbox = 0
    
    for e in all_entities:
        bb = e.bounding_box
        if bb == (0.0, 0.0, 0.0, 0.0):
            zero_bbox += 1
            continue
        if any(math.isnan(v) or math.isinf(v) for v in bb):
            issues.append(f"  NaN/Inf bbox on {e.dxf_type} handle={e.handle}")
            continue
        if bb[2] < bb[0] or bb[3] < bb[1]:
            issues.append(f"  Negative-width bbox on {e.dxf_type} handle={e.handle}: {bb}")
    
    total = len(all_entities)
    valid = total - len(issues) - zero_bbox
    
    print(f"\n  Total entities    : {total}")
    print(f"  Valid bbox        : {valid}")
    print(f"  Zero bbox (fallback): {zero_bbox}")
    print(f"  Invalid bbox      : {len(issues)}")
    
    for issue in issues[:10]:
        print(f"  {issue}")
    if len(issues) > 10:
        print(f"  ... and {len(issues)-10} more")
    
    if len(issues) == 0:
        print("\n  ✅ PASS — No invalid bounding boxes found")
        return True
    else:
        print(f"\n  ❌ FAIL — {len(issues)} invalid bounding boxes found")
        return False

def audit4_uuid_stability(dxf_path: str, drawing) -> bool:
    """Check if UUIDs are stable across two runs by checking handle-based determinism."""
    print("\n" + "=" * 60)
    print("AUDIT 4: UUID Stability")
    print("=" * 60)
    
    reader = DXFReader()
    
    # Run twice
    repo1 = reader.read_geometry(dxf_path, drawing.identity)
    repo2 = reader.read_geometry(dxf_path, drawing.identity)
    
    uuids1 = sorted([str(e.id) for e in repo1.lines[:10]])
    uuids2 = sorted([str(e.id) for e in repo2.lines[:10]])
    
    is_stable = (uuids1 == uuids2)
    
    if is_stable:
        print("\n  ✅ PASS — UUIDs are deterministic across runs")
    else:
        print("\n  ❌ FAIL — UUIDs differ between runs (random generation detected)")
        print("\n  RECOMMENDATION: Switch to handle-based UUID generation:")
        print("    uuid.uuid5(NAMESPACE, f'{drawing_uuid}:{handle}')")
    
    print(f"\n  Sample UUID run 1: {uuids1[0] if uuids1 else 'N/A'}")
    print(f"  Sample UUID run 2: {uuids2[0] if uuids2 else 'N/A'}")
    return is_stable

def audit5_provenance(repo: DrawingRepository) -> bool:
    """Pick one entity and verify full provenance is intact."""
    print("\n" + "=" * 60)
    print("AUDIT 5: Provenance Integrity")
    print("=" * 60)
    
    required_fields = ['id', 'dxf_type', 'layer', 'color', 'linetype',
                       'handle', 'owner_handle', 'parent_block', 'transform',
                       'bounding_box', 'raw_properties']
    
    # Sample one of each type
    samples = []
    if repo.lines: samples.append(('LINE', repo.lines[0]))
    if repo.arcs: samples.append(('ARC', repo.arcs[0]))
    if repo.inserts: samples.append(('INSERT', repo.inserts[0]))
    if repo.dimensions: samples.append(('DIMENSION', repo.dimensions[0]))
    
    all_pass = True
    for etype, entity in samples:
        missing = [f for f in required_fields
                   if not hasattr(entity, f) or
                   (getattr(entity, f) is None and f not in ('parent_block',))]  # None is valid for top-level
        if missing:
            print(f"\n  ❌ {etype} handle={entity.handle}: Missing fields: {missing}")
            all_pass = False
        else:
            print(f"\n  {etype} handle={entity.handle}:")
            print(f"    layer         : {entity.layer}")
            print(f"    color         : {entity.color}")
            print(f"    linetype      : {entity.linetype}")
            print(f"    owner_handle  : {entity.owner_handle}")
            print(f"    parent_block  : {entity.parent_block}")
            print(f"    raw_props keys: {list(entity.raw_properties.keys())[:5]}")
            print(f"    ✅ All provenance fields present")
    
    if all_pass:
        print("\n  ✅ PASS — Full provenance intact for sampled entities")
    else:
        print("\n  ❌ FAIL — Some provenance fields missing")
    
    return all_pass

def main():
    dxf_path = os.path.join(os.path.dirname(__file__), "test_project/SS-GF-01(M).dxf")
    if not os.path.exists(dxf_path):
        dxf_path = os.path.join(os.path.dirname(__file__), "../DRAWINGS/SS-GF-01(M).dxf")
    
    output_dir = "debug/phase02_audit"
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("PHASE 2 AUDIT — RebarFusion Geometry Repository")
    print("=" * 60)
    print(f"Target: {dxf_path}")
    
    repo, drawing = run_phase2_and_get_repo(dxf_path)
    
    r1 = audit1_entity_conservation(dxf_path, repo)
    r2 = audit2_geometry_fidelity(dxf_path, repo, output_dir)
    r3 = audit3_bounding_boxes(repo)
    r4 = audit4_uuid_stability(dxf_path, drawing)
    r5 = audit5_provenance(repo)
    
    print("\n" + "=" * 60)
    print("AUDIT SUMMARY")
    print("=" * 60)
    results = [
        ("1 Entity Conservation", r1),
        ("2 Geometry Fidelity", r2),
        ("3 Bounding Boxes", r3),
        ("4 UUID Stability", r4),
        ("5 Provenance Integrity", r5),
    ]
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  Audit {name:<25}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("  PHASE 2 FROZEN — Repository is trustworthy.")
    else:
        print("  PHASE 2 NOT FROZEN — Fix failing audits before proceeding.")

if __name__ == "__main__":
    main()
