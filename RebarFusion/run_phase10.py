"""
run_phase10.py — Phase 10: Reinforcement Reconstruction
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace
from typing import Any

from core.reconstruction.assembly_builder import AssemblyBuilder
from core.reconstruction.bar_builder import PhysicalBarBuilder
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


def _namespace(value):
    if isinstance(value, dict):
        data = {}
        for key, item in value.items():
            if key.endswith("uuid") or key == "uuid" or key in {"representative_component", "representative_component_uuid"}:
                try:
                    data[key] = uuid.UUID(item)
                    continue
                except Exception:
                    pass
            data[key] = _namespace(item)
        return SimpleNamespace(**data)
    if isinstance(value, list):
        return [_namespace(item) for item in value]
    return value


def _resolve_phase09_file(path: str) -> str:
    if os.path.isfile(path):
        return path
    direct = os.path.join(path, "engineering_families.json")
    if os.path.isfile(direct):
        return direct
    debug_root = os.path.join("debug", "phase09")
    if os.path.isdir(debug_root):
        for root, _, files in os.walk(debug_root):
            if "engineering_families.json" in files:
                return os.path.join(root, "engineering_families.json")
    raise FileNotFoundError("Could not find engineering_families.json. Run Phase 9 first.")


def _output_dir(input_file: str) -> str:
    drawing_name = os.path.basename(os.path.dirname(input_file))
    out_dir = os.path.join("output", "phase10", drawing_name)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


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


def main():
    parser = argparse.ArgumentParser(description="Phase 10: Reinforcement Reconstruction")
    parser.add_argument(
        "input",
        nargs="?",
        default="debug/phase09",
        help="Path to engineering_families.json, a Phase 9 output directory, or a project directory after Phase 9 has run",
    )
    args = parser.parse_args()

    try:
        family_file = _resolve_phase09_file(args.input)
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)

    with open(family_file, "r", encoding="utf-8") as f:
        families = _namespace(json.load(f))

    print("=" * 60)
    print("PHASE 10: REINFORCEMENT RECONSTRUCTION")
    print("=" * 60)
    print(f"Input families: {family_file}")

    assembly_builder = AssemblyBuilder()
    bar_builder = PhysicalBarBuilder()
    mesh_builder = MeshBuilder(segments=12)

    assemblies = assembly_builder.build(families)
    for assembly in assemblies:
        bar_builder.build_for_assembly(assembly)
    meshes = mesh_builder.build_meshes(assemblies)

    out_dir = _output_dir(family_file)
    obj_path = os.path.join(out_dir, "cage.obj")
    ply_path = os.path.join(out_dir, "cage.ply")
    mesh_builder.write_obj(obj_path, meshes)
    mesh_builder.write_ply(ply_path, meshes)

    bars = _bar_payload(assemblies)
    mesh_edge_report = _mesh_edge_report(meshes)
    centerline_count = sum(getattr(family, "detected_count", 0) for family in families)
    assembly_layers = sum(len(assembly.layers) for assembly in assemblies)
    report = {
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
        "Families With Matching Bar Counts": sum(
            1
            for family in families
            if len([bar for bar in bars if str(bar["family_uuid"]) == str(family.uuid)]) == getattr(family, "detected_count", 0)
        ),
        "OBJ": obj_path,
        "PLY": ply_path,
    }

    _jdump(os.path.join(out_dir, "assemblies.json"), _assembly_payload(assemblies))
    _jdump(os.path.join(out_dir, "bars.json"), bars)
    _jdump(os.path.join(out_dir, "meshes.json"), [asdict(mesh) for mesh in meshes])
    _jdump(os.path.join(out_dir, "reconstruction_report.json"), report)

    print("\nReconstruction Summary:")
    for key, value in report.items():
        print(f"  {key:<34} : {value}")

    print("\nValidation Checks:")
    print(f"  Every family produced bars        : {'PASS' if report['Families With Matching Bar Counts'] == len(families) else 'FAIL'}")
    print(f"  Every centerline became a bar     : {'PASS' if report['Phase 10A Centerlines'] == report['Phase 10B Physical Bars'] else 'FAIL'}")
    print(f"  Physical adjustments separated    : {'PASS' if report['Phase 10C Adjusted Bars'] == report['Physical Bars'] else 'FAIL'}")
    print(f"  Meshes watertight                 : {'PASS' if mesh_edge_report['Watertight'] else 'FAIL'}")
    print(f"  Meshes generated                  : {'PASS' if meshes else 'FAIL'}")
    print(f"  OBJ export generated              : {'PASS' if os.path.isfile(obj_path) else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
