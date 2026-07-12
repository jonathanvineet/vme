"""
viewer/workbench_project.py

Data-centric representation of all project information needed by the viewer.
Acts as a single, unified interface to the underlying data, abstracting
away the source (e.g. live pipeline vs. disk-backed JSON bundle).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID
from pathlib import Path

from core.project import DrawingProject
from viewer.project_loader import WorkbenchBundle


@dataclass
class WorkbenchProject:
    """
    A unified container for all project data required by the Engineering Workbench.
    """
    bundle: Optional[WorkbenchBundle] = None

    # Core data repositories
    manifest: Optional[DrawingProject] = None
    canon_repo: Any = None
    node_repo: Any = None
    graph: Any = None
    comp_repo: Any = None
    recognition_cache: Dict[UUID, Any] = field(default_factory=dict)

    # Engineering & Reconstruction data
    engineering_objects: Dict[UUID, Any] = field(default_factory=dict)
    engineering_families: List[Any] = field(default_factory=list)
    reinforcement_assemblies: List[Any] = field(default_factory=list)
    physical_bars: List[Any] = field(default_factory=list)
    reconstruction_meshes: List[Any] = field(default_factory=list)

    # Phase 8 leader reconstruction / Phase 7.6 plausibility (Phase 11.1:
    # the viewer now gets these from core.full_pipeline like everything
    # else, instead of never having them at all).
    leader_repo: Any = None
    plausibility: Dict[UUID, Any] = field(default_factory=dict)

    @property
    def is_loaded(self) -> bool:
        """Check if any substantial data has been loaded."""
        return self.manifest is not None or self.bundle is not None

    @classmethod
    def from_bundle(cls, bundle: WorkbenchBundle) -> WorkbenchProject:
        """Create a WorkbenchProject from a pre-loaded bundle."""
        return cls(
            bundle=bundle,
            manifest=bundle.manifest,
            canon_repo=bundle.canon_repo,
            node_repo=bundle.node_repo,
            graph=bundle.graph,
            comp_repo=bundle.comp_repo,
            recognition_cache=bundle.recognition_cache,
            engineering_objects=bundle.engineering_objects,
            engineering_families=bundle.engineering_families,
            reinforcement_assemblies=bundle.reinforcement_assemblies,
            physical_bars=bundle.physical_bars,
            reconstruction_meshes=bundle.reconstruction_meshes,
        )

    def get_drawing_name(self) -> str:
        if self.bundle:
            return self.bundle.drawing_name
        if self.manifest and self.manifest.drawings:
            # Return the first non-duplicate drawing
            for drawing in self.manifest.drawings.values():
                if not drawing.duplicate_of:
                    return drawing.filename
        return "Untitled Project"
