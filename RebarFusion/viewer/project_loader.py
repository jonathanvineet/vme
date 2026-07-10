from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID
import json

from core.project import DrawingProject


UUID_KEYS = {
    "uuid",
    "family_uuid",
    "assembly_uuid",
    "bar_uuid",
    "member_uuid",
    "component_uuid",
    "representative_component",
    "representative_component_uuid",
    "bar_path_uuid",
    "centerline_uuid",
    "layer_uuid",
    "mesh_uuid",
    "geometry_uuid",
    "start_node_uuid",
    "end_node_uuid",
}

UUID_LIST_KEYS = {
    "family_uuids",
    "bar_uuids",
    "member_component_uuids",
    "member_components",
    "node_ids",
    "edge_ids",
    "connected_entities",
}


@dataclass
class WorkbenchBundle:
    project_root: Path
    manifest: Any
    drawing: Any
    drawing_name: str
    canon_repo: Any
    node_repo: Any
    graph: Any
    comp_repo: Any
    recognition_cache: Dict[UUID, Any]
    engineering_objects: Dict[UUID, Any]
    engineering_families: List[Any]
    reinforcement_assemblies: List[Any]
    physical_bars: List[Any]
    reconstruction_meshes: List[Any]
    phase_reports: Dict[str, Any]


def _to_uuid(value: Any) -> Any:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return value


def _convert(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        data: Dict[str, Any] = {}
        for item_key, item_value in value.items():
            if item_key in UUID_LIST_KEYS and isinstance(item_value, list):
                data[item_key] = [_to_uuid(entry) for entry in item_value]
                continue
            if item_key in UUID_KEYS or item_key.endswith("_uuid") or item_key.endswith("uuid"):
                data[item_key] = _to_uuid(item_value)
                continue
            data[item_key] = _convert(item_value, item_key)
        return SimpleNamespace(**data)
    if isinstance(value, list):
        return [_convert(item, key) for item in value]
    return value


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _search_paths(root: Path, relative_parts: Iterable[str]) -> List[Path]:
    parts = list(relative_parts)
    hits: List[Path] = []
    for base in {root, root.parent, root.parent.parent, Path.cwd(), Path.cwd().parent}:
        if not base.exists():
            continue
        hits.extend(base.glob("/".join(parts)))
    unique: List[Path] = []
    seen = set()
    for path in hits:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _preferred_output(candidates: List[Path], drawing_name: str) -> Optional[Path]:
    if not candidates:
        return None
    drawing_stem = Path(drawing_name).stem.lower()
    drawing_name_lower = drawing_name.lower()
    for candidate in candidates:
        parent_name = candidate.parent.name.lower()
        if parent_name == drawing_name_lower or parent_name == drawing_stem:
            return candidate
    return candidates[0]


def _find_phase_file(root: Path, phase_folder: str, filename: str, drawing_name: str) -> Optional[Path]:
    patterns = [
        Path("debug") / phase_folder / "**" / filename,
        Path("output") / phase_folder / "**" / filename,
    ]
    candidates: List[Path] = []
    for pattern in patterns:
        for base in {root, root.parent, root.parent.parent, Path.cwd(), Path.cwd().parent}:
            if not base.exists():
                continue
            candidates.extend(base.glob(str(pattern)))
    return _preferred_output(candidates, drawing_name)


def _build_canon_repo(data: Dict[str, Any]) -> Any:
    return SimpleNamespace(
        lines=[_convert(item) for item in data.get("lines", [])],
        arcs=[_convert(item) for item in data.get("arcs", [])],
        polylines=[_convert(item) for item in data.get("polylines", [])],
        circles=[_convert(item) for item in data.get("circles", [])],
        texts=[_convert(item) for item in data.get("texts", [])],
        mtexts=[_convert(item) for item in data.get("mtexts", [])],
        dimensions=[_convert(item) for item in data.get("dimensions", [])],
        hatches=[_convert(item) for item in data.get("hatches", [])],
        inserts=[_convert(item) for item in data.get("inserts", [])],
    )


def _build_mapping(data: Dict[str, Any]) -> Dict[UUID, Any]:
    mapping: Dict[UUID, Any] = {}
    for key, value in data.items():
        uid = _to_uuid(key)
        item = _convert(value)
        if hasattr(item, "id"):
            item.id = uid
        mapping[uid] = item
    return mapping


def _build_graph(data: Dict[str, Any]) -> Any:
    nodes = _build_mapping(data.get("nodes", {}))
    edges = _build_mapping(data.get("edges", {}))
    return SimpleNamespace(nodes=nodes, edges=edges)


def _build_component_repo(data: Dict[str, Any]) -> Any:
    return SimpleNamespace(components=_build_mapping(data))


def _load_bundle_file(root: Path, drawing_name: str, phase_folder: str, filename: str) -> Optional[Path]:
    return _find_phase_file(root, phase_folder, filename, drawing_name)


def load_workbench_bundle(project_root: str | Path) -> WorkbenchBundle:
    root = Path(project_root).expanduser().resolve()
    manifest = DrawingProject(name=root.name).load_directory(str(root))

    drawing = None
    for candidate in manifest.drawings.values():
        if candidate.duplicate_of:
            continue
        if candidate.extension.lower() in {"dxf", "dwg", "pdf"}:
            drawing = candidate
            break
    if drawing is None:
        raise FileNotFoundError(f"No supported drawing found in {root}")

    drawing_name = drawing.filename

    phase_reports: Dict[str, Any] = {}

    canon_path = _load_bundle_file(root, drawing_name, "phase03", "canonical_geometry.json")
    graph_path = _load_bundle_file(root, drawing_name, "phase06", "graph.json")
    comp_path = _load_bundle_file(root, drawing_name, "phase06", "components.json")
    recog_path = _load_bundle_file(root, drawing_name, "phase07", "recognition_results.json")
    eng_obj_path = _load_bundle_file(root, drawing_name, "phase08", "engineering_objects.json")
    fam_path = _load_bundle_file(root, drawing_name, "phase09", "engineering_families.json")
    ass_path = _load_bundle_file(root, drawing_name, "phase10", "assemblies.json")
    bar_path = _load_bundle_file(root, drawing_name, "phase10", "bars.json")
    mesh_path = _load_bundle_file(root, drawing_name, "phase10", "meshes.json")
    report_path = _load_bundle_file(root, drawing_name, "phase10", "reconstruction_report.json")

    if report_path:
        phase_reports["phase10"] = _load_json(report_path)

    canon_repo = _build_canon_repo(_load_json(canon_path)) if canon_path else None
    graph = _build_graph(_load_json(graph_path)) if graph_path else None
    comp_repo = _build_component_repo(_load_json(comp_path)) if comp_path else None
    node_repo = SimpleNamespace(nodes=graph.nodes if graph else {})

    recognition_cache: Dict[UUID, Any] = {}
    if recog_path:
        for key, value in _load_json(recog_path).items():
            recognition_cache[_to_uuid(key)] = _convert(value)

    engineering_objects: Dict[UUID, Any] = {}
    if eng_obj_path:
        for key, value in _load_json(eng_obj_path).items():
            engineering_objects[_to_uuid(key)] = _convert(value)

    engineering_families: List[Any] = []
    if fam_path:
        engineering_families = [_convert(item) for item in _load_json(fam_path)]

    reinforcement_assemblies: List[Any] = []
    if ass_path:
        reinforcement_assemblies = [_convert(item) for item in _load_json(ass_path)]

    physical_bars: List[Any] = []
    if bar_path:
        physical_bars = [_convert(item) for item in _load_json(bar_path)]

    reconstruction_meshes: List[Any] = []
    if mesh_path:
        reconstruction_meshes = [_convert(item) for item in _load_json(mesh_path)]

    return WorkbenchBundle(
        project_root=root,
        manifest=manifest,
        drawing=drawing,
        drawing_name=drawing_name,
        canon_repo=canon_repo,
        node_repo=node_repo,
        graph=graph,
        comp_repo=comp_repo,
        recognition_cache=recognition_cache,
        engineering_objects=engineering_objects,
        engineering_families=engineering_families,
        reinforcement_assemblies=reinforcement_assemblies,
        physical_bars=physical_bars,
        reconstruction_meshes=reconstruction_meshes,
        phase_reports=phase_reports,
    )