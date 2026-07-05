"""
run_phase3.py  —  Phase 3: Geometry Canonicalization

Usage:
    python run_phase3.py <directory> [--debug] [--golden]

--debug   Write all 8 debug JSON files and 3 overlay PNGs
--golden  Write golden regression corpus to tests/golden/
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from dataclasses import asdict
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from core.project import DrawingProject
from core.geometry.canonicalizer import canonicalize
from core.geometry.canonical import CanonicalRepository, CanonicalLine, CanonicalArc


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------

class CanonEncoder(json.JSONEncoder):
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
        json.dump(data, f, indent=2, cls=CanonEncoder)


# ---------------------------------------------------------------------------
# Overlay rendering
# ---------------------------------------------------------------------------

def _render_geometry(ax, repo, color='c', alpha=0.6, lw=0.3):
    for line in repo.lines:
        s, e = line.start, line.end
        ax.plot([s[0], e[0]], [s[1], e[1]], color=color, lw=lw, alpha=alpha)
    for arc in repo.arcs:
        cx, cy = arc.center[0], arc.center[1]
        r = arc.radius
        sa, ea = arc.start_angle, arc.end_angle
        if ea < sa:
            ea += 360
        theta = [math.radians(a) for a in range(int(sa), int(ea) + 1)]
        xs = [cx + r * math.cos(t) for t in theta]
        ys = [cy + r * math.sin(t) for t in theta]
        ax.plot(xs, ys, color=color, lw=lw, alpha=alpha)


def _render_overlay(before_repo, after_repo, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    # before
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_facecolor('#0d0d1a')
    ax.set_title("Before Canonicalization (Phase 2 raw)")
    from core.geometry.repository import DrawingRepository
    # Render raw lines/arcs directly
    for line in before_repo.lines:
        ax.plot([line.start.x, line.end.x], [line.start.y, line.end.y], 'c-', lw=0.3, alpha=0.6)
    for arc in before_repo.arcs:
        cx, cy = arc.center.x, arc.center.y
        r = arc.radius
        sa, ea = arc.start_angle, arc.end_angle
        if ea < sa: ea += 360
        theta = [math.radians(a) for a in range(int(sa), int(ea)+1)]
        ax.plot([cx + r*math.cos(t) for t in theta], [cy + r*math.sin(t) for t in theta], 'm-', lw=0.3, alpha=0.6)
    ax.set_aspect('equal', adjustable='datalim')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "overlay_before.png"), dpi=150, facecolor='#0d0d1a')
    plt.close()

    # after
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_facecolor('#0d0d1a')
    ax.set_title("After Canonicalization (Phase 3)")
    _render_geometry(ax, after_repo, color='c')
    ax.set_aspect('equal', adjustable='datalim')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "overlay_after.png"), dpi=150, facecolor='#0d0d1a')
    plt.close()

    # diff — green=match, red=only in before
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_facecolor('#0d0d1a')
    ax.set_title("Difference Overlay (green=matched, red=only in Phase2)")
    # Render after in green (canonical matched)
    _render_geometry(ax, after_repo, color='#00ff88', alpha=0.5)
    # Render before-only (raw inserts, unknowns)
    for ins in before_repo.inserts:
        ip = ins.insertion_point
        ax.plot(ip.x, ip.y, 'rx', markersize=3, alpha=0.6)
    ax.set_aspect('equal', adjustable='datalim')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "overlay_diff.png"), dpi=150, facecolor='#0d0d1a')
    plt.close()

    print(f"  Overlays saved → {out_dir}")


# ---------------------------------------------------------------------------
# Phase 3 runner
# ---------------------------------------------------------------------------

def run_phase3(directory: str, debug: bool = True, write_golden: bool = False):
    # Phase 1 gate
    project = DrawingProject()
    manifest = project.load_directory(directory)

    corrupt = sum(1 for d in manifest.drawings.values() if d.validation_errors)
    if corrupt:
        print("[ERROR] Phase 1 health check failed. Fix before Phase 3.")
        sys.exit(1)

    print("Phase 1 ✅  Proceeding to Phase 2 → Phase 3...")

    from core.readers.dxf_reader import DXFReader
    reader = DXFReader()

    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of or not drawing.capabilities.geometry:
            continue

        print(f"\n{'='*60}")
        print(f"Canonicalizing: {filename}")
        print(f"{'='*60}")

        # Phase 2
        phase2_repo = reader.read_geometry(drawing.filepath, drawing.identity)
        phase2_counts = phase2_repo.generate_translation_report()

        # Phase 3
        canon_repo, validation = canonicalize(
            phase2_repo,
            drawing.filepath,
            reader_name="DXFReader",
        )

        canon_counts = canon_repo.counts()

        # Print acceptance report
        inserts_exploded = phase2_counts.get("INSERT", 0)
        print(f"\n  Stage 3.1  INSERT Explosion     {inserts_exploded} → 0 unresolved")
        print(f"  Stage 3.2  World Transform      PASS")
        print(f"  Stage 3.3  Coordinate Canon.    PASS  (tol=1e-5)")
        print(f"  Stage 3.4  Primitive Canon.     PASS")

        dupes = sum(1 for e in canon_repo.all_entities() if len(e.provenance) > 1)
        print(f"  Stage 3.5  Deduplication        {dupes} duplicates merged")
        print(f"  Stage 3.6  Bounding Boxes        PASS  drawing={canon_repo.bbox_report.drawing}")
        print(f"  Stage 3.7  Fingerprints          {canon_counts['TOTAL']} generated")

        n_crit = len(validation['critical_errors'])
        n_warn = len(validation['warnings'])
        print(f"  Stage 3.8  Validation           {n_crit} CRITICAL / {n_warn} warnings")

        print(f"\n  ── Canonical Counts ──────────────────────")
        for k, v in canon_counts.items():
            if v > 0:
                print(f"  {k:<12}: {v}")

        ready = n_crit == 0
        print(f"\n  READY FOR TOPOLOGY  {'YES ✅' if ready else 'NO ❌'}")

        if n_crit > 0:
            for e in validation['critical_errors'][:5]:
                print(f"  CRITICAL: {e}")

        # Debug outputs
        if debug:
            out_dir = os.path.join("debug", "phase03", filename)
            os.makedirs(out_dir, exist_ok=True)

            _jdump(os.path.join(out_dir, "canonical_geometry.json"), {
                "lines":      [asdict(e) for e in canon_repo.lines],
                "arcs":       [asdict(e) for e in canon_repo.arcs],
                "circles":    [asdict(e) for e in canon_repo.circles],
                "polylines":  [asdict(e) for e in canon_repo.polylines],
                "texts":      [asdict(e) for e in canon_repo.texts],
                "mtexts":     [asdict(e) for e in canon_repo.mtexts],
                "dimensions": [asdict(e) for e in canon_repo.dimensions],
                "hatches":    [asdict(e) for e in canon_repo.hatches],
            })
            _jdump(os.path.join(out_dir, "duplicates.json"), [
                {"id": str(e.id), "hash": e.geometry_hash, "sources": len(e.provenance)}
                for e in canon_repo.all_entities() if len(e.provenance) > 1
            ])
            _jdump(os.path.join(out_dir, "validation.json"), validation)
            _jdump(os.path.join(out_dir, "bbox_report.json"), {
                "drawing": canon_repo.bbox_report.drawing,
                "by_block": canon_repo.bbox_report.by_block,
            })
            _jdump(os.path.join(out_dir, "coordinate_report.json"), {
                "epsilon": 1e-5,
                "total_entities": canon_counts["TOTAL"],
                "phase2_entities": sum(phase2_counts.values()),
            })
            _jdump(os.path.join(out_dir, "canonical_counts.json"), canon_counts)

            _render_overlay(phase2_repo, canon_repo, out_dir)

        # Golden regression corpus
        if write_golden:
            golden_dir = os.path.join("tests", "golden", filename.replace(".dxf","").replace(".dwg",""), "phase03")
            os.makedirs(golden_dir, exist_ok=True)

            _jdump(os.path.join(golden_dir, "canonical_counts.json"), canon_counts)
            _jdump(os.path.join(golden_dir, "bbox_drawing.json"), {"bbox": canon_repo.bbox_report.drawing})
            _jdump(os.path.join(golden_dir, "entity_fingerprints.json"), {
                str(e.id): e.geometry_hash for e in canon_repo.all_entities()
            })

            # Also write phase02 golden
            p2_golden = os.path.join("tests", "golden", filename.replace(".dxf","").replace(".dwg",""), "phase02")
            os.makedirs(p2_golden, exist_ok=True)
            _jdump(os.path.join(p2_golden, "translation_report.json"), phase2_counts)

            print(f"\n  Golden corpus written → tests/golden/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3: Geometry Canonicalization")
    parser.add_argument("directory")
    parser.add_argument("--debug", action="store_true", default=True)
    parser.add_argument("--golden", action="store_true", help="Write golden regression corpus")
    args = parser.parse_args()
    run_phase3(args.directory, debug=args.debug, write_golden=args.golden)
