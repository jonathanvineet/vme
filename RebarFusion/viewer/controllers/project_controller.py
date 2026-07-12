"""
viewer/controllers/project_controller.py

Project loading and data pipeline orchestration.

Phase 11.1: this now calls core.full_pipeline.run_full_pipeline -- the same
function run_phase10.py calls -- instead of maintaining its own copy of the
recognizer/association/family/reconstruction wiring. The previous
"_run_legacy_pipeline" had silently drifted out of sync with the CLI (raw
ezdxf leader scanning, no Phase 7.6 plausibility filter, no Phase 10
geometry recovery -- see docs/audits/phase11/11.0_viewer_audit.md). There
is now exactly one pipeline implementation; the viewer is just a caller.
"""
import traceback

from PySide6.QtCore import QObject, Signal

from viewer.project_loader import load_workbench_bundle
from viewer.workbench_project import WorkbenchProject

from core.full_pipeline import run_full_pipeline


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

        Tries a pre-computed, version-checked "workbench bundle" first (see
        viewer/project_loader.py). If none is available or it fails a
        version check, runs the live pipeline (core.full_pipeline) --
        never a viewer-local reimplementation of it.
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
            self.log_message.emit(f"[INFO] Saved bundle unavailable or incompatible: {bundle_error}")

        try:
            project = self._run_live_pipeline(directory)
            self.status_message.emit(f"Loaded: {directory}")
            self.project_loaded.emit(project)

        except Exception as e:
            error_msg = f"Error: {e}"
            self.status_message.emit(error_msg)
            self.log_message.emit(f"[ERROR] {e}")
            self.log_message.emit(traceback.format_exc())
            self.project_load_failed.emit(error_msg)

    def _run_live_pipeline(self, directory: str) -> WorkbenchProject:
        """Runs core.full_pipeline.run_full_pipeline -- the same Phase 1-10
        pipeline run_phase10.py uses -- and adapts its result onto
        WorkbenchProject. No engineering/reconstruction logic lives here."""
        self.log_message.emit("[INFO] Running live pipeline (core.full_pipeline)...")

        for result in run_full_pipeline(directory, segments=12):
            wp = WorkbenchProject(
                manifest=result.manifest,
                canon_repo=result.canon_repo,
                node_repo=result.node_repo,
                graph=result.graph,
                comp_repo=result.comp_repo,
                recognition_cache=result.recognition_cache,
                engineering_objects=result.engineering_objects,
                engineering_families=result.engineering_families,
                reinforcement_assemblies=result.reinforcement_assemblies,
                physical_bars=result.physical_bars,
                reconstruction_meshes=result.reconstruction_meshes,
                leader_repo=result.leader_repo,
                plausibility=result.plausibility,
            )

            self.log_message.emit(f"Loaded: {result.filename}")
            self.log_message.emit(
                f"  Nodes={len(result.graph.nodes)}  Edges={len(result.graph.edges)}  Components={len(result.comp_repo.components)}"
            )
            self.log_message.emit(f"  Engineering Families={len(wp.engineering_families)}")
            self.log_message.emit(f"  Reinforcement Assemblies={len(wp.reinforcement_assemblies)}  Bars={len(wp.physical_bars)}")
            return wp  # Only process the first drawing for now

        raise FileNotFoundError(f"No drawings with geometry found in {directory}")
