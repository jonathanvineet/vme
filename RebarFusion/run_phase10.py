"""
run_phase10.py — Phase 10: Reinforcement Reconstruction
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from core.full_pipeline import run_full_pipeline, PIPELINE_VERSION
from core.reconstruction.mesh_builder import MeshBuilder


class ReconstructionEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, SimpleNamespace):
            return obj.__dict__
        return super().default(obj)


def _jdump(path: str, obj: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, cls=ReconstructionEncoder)


def _assembly_payload(assemblies):
    payload = []
    for assembly in assemblies:
        item = asdict(assembly)
        item["families"] = [str(f.uuid) for f in assembly.families]
        payload.append(item)
    return payload


def _bar_payload(assemblies):
    return [asdict(bar) for assembly in assemblies for bar in assembly.bars]


def _mesh_edge_report(meshes):
    open_edges = 0
    nonmanifold_edges = 0
    for mesh in meshes:
        counts = {}
        for face in mesh.faces:
            a, b, c = face
            for edge in ((a, b), (b, c), (c, a)):
                key = tuple(sorted(edge))
                counts[key] = counts.get(key, 0) + 1
        open_edges += sum(1 for count in counts.values() if count == 1)
        nonmanifold_edges += sum(1 for count in counts.values() if count > 2)
    return {
        "Open Edges": open_edges,
        "Nonmanifold Edges": nonmanifold_edges,
        "Watertight": open_edges == 0 and nonmanifold_edges == 0,
    }

def _mesh_topology_report(mesh):
    """
    Phase 10.2 acceptance checks beyond open/nonmanifold edges: connected
    component count (a continuous tube sweep should be exactly 1 per bar --
    the old per-segment-capped approach could produce multiple touching
    solids that only share vertices, not edges) and vertex/face counts
    versus the closed-form formula from
    docs/audits/phase10/10.2_continuous_tube_sweep.md.
    """
    # Union-find over vertices connected by a shared face edge.
    parent = list(range(len(mesh.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for a, b, c in mesh.faces:
        union(a, b)
        union(b, c)

    used_vertices = {v for face in mesh.faces for v in face}
    components = len({find(v) for v in used_vertices}) if used_vertices else 0
    return {"connected_components": components, "vertex_count": len(mesh.vertices), "face_count": len(mesh.faces)}


def _polyline_length(points) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5
    return total


def _generate_debug_report(out_dir: str, families, assemblies, meshes):
    """Generates a detailed, human-readable debug report."""
    report_path = os.path.join(out_dir, "debug_report.txt")
    bars = [bar for asm in assemblies for bar in asm.bars]
    bar_map = {bar.uuid: bar for bar in bars}

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("PHASE 10 DEBUG REPORT\n")
        f.write("=" * 80 + "\n\n")

        f.write("Stage 1: Input Families\n")
        f.write("-" * 80 + "\n")
        for i, family in enumerate(families):
            f.write(f"Family {i+1}:\n")
            f.write(f"  Mark            : {getattr(family, 'mark', 'N/A')}\n")
            f.write(f"  Members         : {getattr(family, 'detected_count', 0)}\n")
            f.write(f"  Spacing         : {getattr(family, 'spacing', 0):.1f}\n")
            f.write(f"  Diameter        : {getattr(family, 'diameter', 0)}\n")
            f.write(f"  Shape           : {getattr(family, 'recognition_type', 'N/A')}\n")
            f.write(f"  Length          : {getattr(family, 'length', 0):.1f}\n\n")

        f.write("\nStage 2-7: Per-Bar Reconstruction Details\n")
        f.write("-" * 80 + "\n")
        for i, mesh in enumerate(meshes):
            bar = bar_map.get(mesh.bar_uuid)
            if not bar:
                continue

            f.write(f"BAR {i+1} (UUID: {str(bar.uuid)[:8]}...)\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Centerline Length : {_polyline_length(bar.path):.1f} mm\n")
            f.write(f"  Radius            : {bar.diameter / 2.0} mm\n")
            f.write(f"  Vertices Generated: {len(mesh.vertices)}\n")
            f.write(f"  Triangles Generated: {len(mesh.faces)}\n")
            
            if mesh.vertices:
                points = np.array(mesh.vertices)
                min_pt, max_pt = points.min(axis=0), points.max(axis=0)
                f.write("  Mesh Bounds:\n")
                f.write(f"    xmin: {min_pt[0]:.2f}, xmax: {max_pt[0]:.2f}\n")
                f.write(f"    ymin: {min_pt[1]:.2f}, ymax: {max_pt[1]:.2f}\n")
                f.write(f"    zmin: {min_pt[2]:.2f}, zmax: {max_pt[2]:.2f}\n")
            
            edge_report = _mesh_edge_report([mesh])
            f.write(f"  Watertight        : {'YES' if edge_report['Watertight'] else 'NO'}\n")
            
            obj_path = os.path.join(out_dir, f"{i+1:04d}.obj")
            f.write(f"  OBJ Written       : {'YES' if os.path.exists(obj_path) else 'NO'}\n\n")

def _plot_centerlines(assemblies, out_path):
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.set_title("Stage 2: Generated Centerlines (2D)")
    ax.set_aspect('equal')
    ax.set_facecolor('#0d0d1a')
    for asm in assemblies:
        for bar in asm.bars:
            path = np.array(bar.path)
            ax.plot(path[:, 0], path[:, 1], lw=1)
    plt.savefig(out_path, dpi=150)
    plt.close(fig)

def _plot_3d(meshes, out_path, as_wireframe=False):
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_title("Stage 3/4: 3D Bars/Meshes")
    ax.set_facecolor('#0d0d1a')

    for mesh in meshes:
        if not mesh.vertices: continue
        points = np.array(mesh.vertices)
        if as_wireframe:
            for face in mesh.faces:
                verts = points[face, :]
                verts = np.vstack([verts, verts[0,:]]) # close loop
                ax.plot(verts[:,0], verts[:,1], verts[:,2], color='c', lw=0.5)
        else:
            # Plot as cylinders (approximated by plotting centerlines with thickness)
            bar_path = points[[0, -1], :] # Simplified for this plot
            ax.plot(bar_path[:,0], bar_path[:,1], bar_path[:,2], lw=4)

    # Auto-scale axes
    all_verts = np.vstack([np.array(m.vertices) for m in meshes if m.vertices])
    if all_verts.size > 0:
        min_pt, max_pt = all_verts.min(axis=0), all_verts.max(axis=0)
        center = (min_pt + max_pt) / 2
        max_range = (max_pt - min_pt).max()
        ax.set_xlim(center[0] - max_range/2, center[0] + max_range/2)
        ax.set_ylim(center[1] - max_range/2, center[1] + max_range/2)
        ax.set_zlim(center[2] - max_range/2, center[2] + max_range/2)

    plt.savefig(out_path, dpi=150)
    plt.close(fig)



def main():
    parser = argparse.ArgumentParser(description="Phase 10: Reinforcement Reconstruction")
    parser.add_argument(
        "input",
        nargs="?",
        default="test_project",
        help="Path to a project directory. Phases 1-10 are run via "
             "core.full_pipeline.run_full_pipeline -- the same function the "
             "viewer calls, so both stay in sync.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to generate detailed intermediate files and reports."
    )
    args = parser.parse_args()

    try:
        pipeline_runs = list(run_full_pipeline(args.input, segments=12))
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)
    if not pipeline_runs:
        print(f"No drawings with geometry found in {args.input}")
        sys.exit(1)
    result = pipeline_runs[0]
    filename = result.filename
    families = result.engineering_families
    graph = result.graph
    comp_repo = result.comp_repo
    entity_by_geom_id = result.entity_by_geom_id
    assemblies = result.reinforcement_assemblies
    meshes = result.reconstruction_meshes

    out_dir = os.path.join("debug" if args.debug else "output", "phase10", filename)
    if args.debug and os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print("PHASE 10: REINFORCEMENT RECONSTRUCTION")
    print("=" * 60)
    print(f"Input drawing: {filename}  ({len(families)} families rebuilt live from Phases 1-9)")
    if args.debug:
        print("DEBUG MODE ENABLED")
        _jdump(os.path.join(out_dir, "00_input_families.json"), [asdict(f) for f in families])

    # I/O only (OBJ/PLY writers) -- the mesh geometry itself came from
    # run_full_pipeline() above, not built here.
    mesh_builder = MeshBuilder(segments=12)

    if args.debug:
        _jdump(os.path.join(out_dir, "01_physical_bars.json"), _bar_payload(assemblies))
        _jdump(os.path.join(out_dir, "02_meshes.json"), [asdict(m) for m in meshes])
        _plot_centerlines(assemblies, os.path.join(out_dir, "centerlines.png"))
        _plot_3d(meshes, os.path.join(out_dir, "bars_3d.png"), as_wireframe=False)
        _plot_3d(meshes, os.path.join(out_dir, "mesh_wireframe.png"), as_wireframe=True)
        # For individual OBJs
        for i, mesh in enumerate(meshes):
            mesh_builder.write_obj(os.path.join(out_dir, f"{i+1:04d}.obj"), [mesh])
        _generate_debug_report(out_dir, families, assemblies, meshes)
    else:
        obj_path = os.path.join(out_dir, "cage.obj")
        ply_path = os.path.join(out_dir, "cage.ply")
        mesh_builder.write_obj(obj_path, meshes)
        mesh_builder.write_ply(ply_path, meshes)

    # Final summary report (always generated)
    bars = _bar_payload(assemblies)
    mesh_edge_report = _mesh_edge_report(meshes)
    topology_reports = [_mesh_topology_report(m) for m in meshes]
    multi_component_meshes = sum(1 for t in topology_reports if t["connected_components"] > 1)
    centerline_count = sum(getattr(family, "detected_count", 0) for family in families)
    assembly_layers = sum(len(assembly.layers) for assembly in assemblies)
    # Always compute the full report -- it feeds both the printed summary
    # and the validation checks below, so suppressing it in debug mode (as
    # the previous `if not args.debug else {}` did) silently broke the
    # validation gate whenever --debug was passed, independent of whether
    # reconstruction actually succeeded.
    report = {
        "pipeline_version": PIPELINE_VERSION,
        "Phase 10A Centerlines": centerline_count,
        "Phase 10B Physical Bars": len(bars),
        "Phase 10C Adjusted Bars": sum(1 for bar in bars if bar["adjustment_notes"]),
        "Engineering Families": len(families),
        "Reinforcement Assemblies": len(assemblies),
        "Assembly Layers": assembly_layers,
        "Physical Bars": len(bars),
        "Meshes": len(meshes),
        "Vertices": sum(len(mesh.vertices) for mesh in meshes),
        "Faces": sum(len(mesh.faces) for mesh in meshes),
        "Mesh Edge Report": mesh_edge_report,
        "Multi-Component Meshes (should be 0 -- one continuous tube per bar)": multi_component_meshes,
        "Families With Matching Bar Counts": sum(
            1
            for family in families
            if len([bar for bar in bars if str(bar["family_uuid"]) == str(family.uuid)]) == getattr(family, "detected_count", 0)
        ),
    }
    if not args.debug:
        report["OBJ"] = obj_path
        report["PLY"] = ply_path

    _jdump(os.path.join(out_dir, "assemblies.json"), _assembly_payload(assemblies))
    _jdump(os.path.join(out_dir, "bars.json"), bars)
    _jdump(os.path.join(out_dir, "meshes.json"), [asdict(mesh) for mesh in meshes])
    _jdump(os.path.join(out_dir, "reconstruction_report.json"), report)

    print("\nReconstruction Summary:")
    if report:
        for key, value in report.items():
            print(f"  {key:<34} : {value}")

    print("\nValidation Checks:")
    print(f"  Every family produced bars        : {'PASS' if report.get('Families With Matching Bar Counts', 0) == len(families) else 'FAIL'}")
    print(f"  Every centerline became a bar     : {'PASS' if report.get('Phase 10A Centerlines', 0) == report.get('Phase 10B Physical Bars', -1) else 'FAIL'}")
    print(f"  Meshes watertight                 : {'PASS' if mesh_edge_report['Watertight'] else 'FAIL'}")
    print(f"  Meshes generated                  : {'PASS' if meshes else 'FAIL'}")
    print(f"  One continuous mesh per bar       : {'PASS' if multi_component_meshes == 0 else 'FAIL'}")
    if not args.debug:
        print(f"  OBJ export generated              : {'PASS' if os.path.isfile(obj_path) else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
