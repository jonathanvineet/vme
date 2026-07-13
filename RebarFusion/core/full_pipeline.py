"""
core/full_pipeline.py — the single, canonical Phase 1-10 pipeline.

Both `run_phase10.py` (CLI) and `viewer/controllers/project_controller.py`
(the viewer) call these functions instead of each maintaining their own
copy of the recognizer registry / association / family-building /
reconstruction wiring. Before this module existed, the viewer had its own
`_run_legacy_pipeline` that had silently drifted out of sync with the CLI
(see docs/audits/phase11/11.0_viewer_audit.md: raw ezdxf leader scanning,
no Phase 7.6 plausibility filter, no Phase 10 geometry recovery) --
duplicated logic is exactly how that kind of drift happens. There is now
exactly one implementation; the viewer and CLI are both just callers of it.

Note: not named core/pipeline.py -- that filename is already used by an
unrelated, older prototype architecture (core/engine.py, core/context.py,
core/geometry/parser.py/normalizer.py), itself unreferenced by any of the
actual run_phaseN.py scripts but still imported by a few other legacy
modules, so left untouched rather than overwritten.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from core.project import DrawingProject
from core.geometry.canonicalizer import canonicalize
from core.spatial.engine import SpatialQueryEngine
from core.topology.node_builder import build_nodes
from core.topology.builder import TopologyBuilder
from core.recognition.registry import RecognizerRegistry, RecognitionCache
from core.recognition.recognizers import (
    StraightBarRecognizer, LBarRecognizer, UBarRecognizer, ClosedShapeRecognizer,
    BranchRecognizer, StructuralOutlineRecognizer, DimensionRecognizer, LeaderRecognizer,
)
from core.recognition.annotations import Annotation, AnnotationParser
from core.recognition.leaders import reconstruct_leaders, LeaderRepository
from core.recognition.plausibility import evaluate_plausibility
from core.engineering.association import EngineeringAssociationEngine
from core.engineering.solver import ConstraintSolver
from core.engineering.family import FamilyBuilder
from core.reconstruction.assembly_builder import AssemblyBuilder
from core.reconstruction.bar_builder import PhysicalBarBuilder
from core.reconstruction.mesh_builder import MeshBuilder

# Bumped whenever the shape of PipelineResult, or the semantics of the data
# it carries, changes in a way that would make an old cached/serialized
# result unsafe to load as if it were current (see Phase 11.1 Step 5 /
# viewer/project_loader.py's version check).
PIPELINE_VERSION = "10.4"

BAR_SHAPE_LABELS = {"straight_bar", "l_bar", "u_bar", "stirrup", "branch"}


@dataclass
class PipelineResult:
    filename: str
    manifest: Any
    canon_repo: Any
    node_repo: Any
    graph: Any
    comp_repo: Any
    entity_by_geom_id: Dict[uuid.UUID, Any]
    recognition_cache: RecognitionCache
    plausibility: Dict[uuid.UUID, Any]
    leader_repo: LeaderRepository
    engineering_objects: Dict[uuid.UUID, Any]
    engineering_families: List[Any]
    reinforcement_assemblies: Optional[List[Any]] = None
    physical_bars: Optional[List[Any]] = None
    reconstruction_meshes: Optional[List[Any]] = None


def _new_registry() -> RecognizerRegistry:
    registry = RecognizerRegistry()
    for r in [StraightBarRecognizer(), LBarRecognizer(), UBarRecognizer(), ClosedShapeRecognizer(),
              BranchRecognizer(), StructuralOutlineRecognizer(), DimensionRecognizer(), LeaderRecognizer()]:
        registry.register(r)
    return registry


def run_pipeline_through_phase9(directory: str) -> Iterator[PipelineResult]:
    """
    Phases 1-9: project load through engineering family building. Yields one
    PipelineResult per non-duplicate drawing with geometry capability.
    `reinforcement_assemblies`/`physical_bars`/`reconstruction_meshes` are
    left None -- call `build_reconstruction()` (Phase 10) if needed.
    """
    project = DrawingProject()
    manifest = project.load_directory(directory)
    if not manifest:
        raise FileNotFoundError(f"Failed to load project directory: {directory}")

    registry = _new_registry()

    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of or not drawing.capabilities.geometry:
            continue

        # Same reader dispatch as Phase 1's metadata pass -- a .dwg gets
        # the DWGReader (ODA conversion + DXFReader), everything else the
        # DXFReader directly. One geometry-extraction path either way.
        # canonicalize() re-opens the file with ezdxf itself, so for DWG
        # input both stages must be handed the same converted-DXF path,
        # not the original .dwg.
        reader = project._get_reader(drawing.filepath)
        if reader is None:
            continue
        geometry_path = drawing.filepath
        if drawing.extension == "dwg":
            from core.readers.dwg_converter import convert_dwg_to_dxf
            geometry_path = convert_dwg_to_dxf(drawing.filepath)

        phase2 = reader.read_geometry(drawing.filepath, drawing.identity)
        canon_repo, _ = canonicalize(phase2, geometry_path)
        engine = SpatialQueryEngine.build(canon_repo)
        node_repo, _, _ = build_nodes(canon_repo, engine, filename)
        builder = TopologyBuilder(node_repo, canon_repo)
        graph, comp_repo, _, _ = builder.build()

        cache = RecognitionCache()
        for comp in comp_repo.components.values():
            cache.set(comp.id, registry.evaluate(comp, graph))

        plausibility_records = {
            comp.id: {"label": cache.get(comp.id).label, "length": float(comp.statistics.get("total_length", 0.0))}
            for comp in comp_repo.components.values()
            if cache.get(comp.id) and cache.get(comp.id).label in BAR_SHAPE_LABELS
        }
        plausibility = evaluate_plausibility(plausibility_records)

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
        for group in groups:
            if not group.tokens:
                continue
            candidates = assoc_engine.find_group_candidates(group, k=5)
            if candidates:
                for c in assoc_engine.build_constraints(candidates):
                    solver.add_constraint(c)
        eng_objects = solver.solve()

        family_builder = FamilyBuilder(graph, comp_repo, engine, cache)
        families = family_builder.build_families(eng_objects)

        entity_by_geom_id = {}
        for l in canon_repo.lines:
            entity_by_geom_id[l.id] = l
        for a in canon_repo.arcs:
            entity_by_geom_id[a.id] = a
        for p in canon_repo.polylines:
            entity_by_geom_id[p.id] = p

        yield PipelineResult(
            filename=filename, manifest=manifest, canon_repo=canon_repo, node_repo=node_repo,
            graph=graph, comp_repo=comp_repo, entity_by_geom_id=entity_by_geom_id,
            recognition_cache=cache, plausibility=plausibility, leader_repo=leader_repo,
            engineering_objects=eng_objects, engineering_families=families,
        )


def build_reconstruction(result: PipelineResult, segments: int = 12) -> PipelineResult:
    """Phase 10: assemblies, physical bars (with real geometry recovery), meshes
    (continuous tube sweep). Mutates and returns the same PipelineResult."""
    assembly_builder = AssemblyBuilder()
    bar_builder = PhysicalBarBuilder()
    mesh_builder = MeshBuilder(segments=segments)

    assemblies = assembly_builder.build(result.engineering_families)
    for assembly in assemblies:
        bar_builder.build_for_assembly(
            assembly, graph=result.graph, entity_by_geom_id=result.entity_by_geom_id, comp_repo=result.comp_repo
        )
    meshes = mesh_builder.build_meshes(assemblies)

    result.reinforcement_assemblies = assemblies
    result.physical_bars = [bar for assembly in assemblies for bar in assembly.bars]
    result.reconstruction_meshes = meshes
    return result


def run_full_pipeline(directory: str, segments: int = 12) -> Iterator[PipelineResult]:
    """Phases 1-10 end to end. This is what run_phase10.py and the viewer
    should both call -- see module docstring."""
    for result in run_pipeline_through_phase9(directory):
        yield build_reconstruction(result, segments=segments)
