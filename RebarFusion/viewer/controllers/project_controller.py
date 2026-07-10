"""
viewer/controllers/project_controller.py

Project loading and data pipeline orchestration.
"""
import traceback
import uuid
import ezdxf

from PySide6.QtCore import QObject, Signal

from viewer.project_loader import load_workbench_bundle
from viewer.workbench_project import WorkbenchProject

# --- Imports from the legacy loading path ---
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
from core.reconstruction.assembly_builder import AssemblyBuilder
from core.reconstruction.bar_builder import PhysicalBarBuilder
from core.reconstruction.mesh_builder import MeshBuilder


class ProjectController(QObject):
    """
    Handles loading and managing project data.
    Orchestrates the data loading pipeline and informs the UI of the results.
    """
    project_loaded = Signal(object)  # Emits WorkbenchProject
    project_load_failed = Signal(str)
    log_message = Signal(str)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def load_project(self, directory: str):
        """
        Loads a project from a directory.

        It first tries to load a pre-computed "workbench bundle". If that fails,
        it falls back to running the full, in-process legacy pipeline.
        """
        self.status_message.emit(f"Loading {directory}…")

        try:
            bundle = load_workbench_bundle(directory)
            project = WorkbenchProject.from_bundle(bundle)

            self.log_message.emit(f"Loaded bundle: {project.get_drawing_name()}")
            self.log_message.emit(f"  Families={len(project.engineering_families)}  Assemblies={len(project.reinforcement_assemblies)}  Bars={len(project.physical_bars)}")
            self.log_message.emit(f"  Meshes={len(project.reconstruction_meshes)}")
            self.status_message.emit(f"Loaded: {directory}")
            self.project_loaded.emit(project)
            return
        except Exception as bundle_error:
            self.log_message.emit(f"[INFO] Saved bundle loader unavailable: {bundle_error}")

        # Legacy fallback: recompute everything in-process from the drawing.
        try:
            project = self._run_legacy_pipeline(directory)
            self.status_message.emit(f"Loaded: {directory}")
            self.project_loaded.emit(project)

        except Exception as e:
            error_msg = f"Error: {e}"
            self.status_message.emit(error_msg)
            self.log_message.emit(f"[ERROR] {e}")
            self.log_message.emit(traceback.format_exc())
            self.project_load_failed.emit(error_msg)

    def _run_legacy_pipeline(self, directory: str) -> WorkbenchProject:
        """The original, in-process data processing pipeline."""
        self.log_message.emit("[INFO] Running legacy in-process pipeline...")
        
        project_state = DrawingProject()
        manifest = project_state.load_directory(directory)
        reader = DXFReader()

        wp = WorkbenchProject(manifest=manifest)

        registry = RecognizerRegistry()
        registry.register(StraightBarRecognizer())
        registry.register(LBarRecognizer())
        registry.register(UBarRecognizer())
        registry.register(StirrupRecognizer())
        registry.register(BranchRecognizer())
        registry.register(StructuralOutlineRecognizer())
        registry.register(DimensionRecognizer())
        registry.register(LeaderRecognizer())

        # Load first supported drawing (extendable to multi-drawing overlay)
        for filename, drawing in manifest.drawings.items():
            if drawing.duplicate_of or not drawing.capabilities.geometry:
                continue
            
            phase2 = reader.read_geometry(drawing.filepath, drawing.identity)
            wp.canon_repo, _ = canonicalize(phase2, drawing.filepath)
            engine = SpatialQueryEngine.build(wp.canon_repo)
            wp.node_repo, _, _ = build_nodes(wp.canon_repo, engine, filename)
            builder = TopologyBuilder(wp.node_repo, wp.canon_repo)
            wp.graph, wp.comp_repo, metrics, _ = builder.build()

            wp.recognition_cache = RecognitionCache()
            for comp in wp.comp_repo.components.values():
                result = registry.evaluate(comp, wp.graph)
                wp.recognition_cache.set(comp.id, result)

            annotations = []
            for t in wp.canon_repo.texts:
                annotations.append(Annotation(uuid.uuid4(), 'TEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
            for t in wp.canon_repo.mtexts:
                annotations.append(Annotation(uuid.uuid4(), 'MTEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
            for d in wp.canon_repo.dimensions:
                annotations.append(Annotation(uuid.uuid4(), 'DIMENSION', d.text, d.defpoint, d.bounding_box, 0.0, d.layer, d.id, d.measurement, d.p1, d.p2))

            leaders = []
            doc = ezdxf.readfile(drawing.filepath)
            msp = doc.modelspace()
            for e in msp:
                if e.dxftype() == 'LINE' and e.dxf.layer == 'G-ANNO-TEXT':
                    leaders.append(((e.dxf.start.x, e.dxf.start.y, e.dxf.start.z), (e.dxf.end.x, e.dxf.end.y, e.dxf.end.z)))

            assoc_engine = EngineeringAssociationEngine(wp.graph, wp.comp_repo, engine, wp.recognition_cache)
            anno_parser = AnnotationParser()
            groups = assoc_engine.cluster_annotations(annotations, anno_parser, leaders)

            solver = ConstraintSolver()
            for group in groups:
                if not group.tokens:
                    continue
                candidates = assoc_engine.find_group_candidates(group, k=5)
                if candidates:
                    constraints = assoc_engine.build_constraints(candidates)
                    for c in constraints:
                        solver.add_constraint(c)

            wp.engineering_objects = solver.solve()
            family_builder = FamilyBuilder(wp.graph, wp.comp_repo, engine, wp.recognition_cache)
            wp.engineering_families = family_builder.build_families(wp.engineering_objects)
            wp.reinforcement_assemblies = AssemblyBuilder().build(wp.engineering_families)
            bar_builder = PhysicalBarBuilder()
            for assembly in wp.reinforcement_assemblies:
                bar_builder.build_for_assembly(assembly)
            
            wp.physical_bars = [bar for assembly in wp.reinforcement_assemblies for bar in assembly.bars]
            wp.reconstruction_meshes = MeshBuilder(segments=12).build_meshes(wp.reinforcement_assemblies)

            self.log_message.emit(f"Loaded: {filename}")
            self.log_message.emit(f"  Nodes={metrics['total_nodes']}  Edges={metrics['total_edges']}  Components={metrics['connected_components']}")
            self.log_message.emit(f"  Engineering Families={len(wp.engineering_families)}")
            self.log_message.emit(f"  Reinforcement Assemblies={len(wp.reinforcement_assemblies)}  Bars={len(wp.physical_bars)}")
            break # Only process one drawing for now

        return wp
