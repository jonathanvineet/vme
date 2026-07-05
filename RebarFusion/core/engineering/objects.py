"""
core/engineering.py

Engineering object progression:
    RecognizedBar → AnnotatedBar → RebarGroup → RebarModel
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any
from core.geometry.entities import Point


# ─── Phase 7 output ──────────────────────────────────────────────────────────

@dataclass
class RecognitionResult:
    """Returned by every recognizer. Best confidence wins per component."""
    type: str               # "straight_bar" | "l_bar" | "u_bar" | "stirrup"
                            # | "dimension" | "leader" | "text_frame"
                            # | "symbol" | "unknown"
    confidence: float       # 0.0 – 1.0
    fingerprint: str        # e.g. "L2-A0-V2-4578-O"
    reason: str             # human-readable explanation
    recognizer: str         # class name that produced this result
    geometry: Any = None    # the ConnectedComponent


@dataclass
class RecognizedBar:
    """Pure geometry — no engineering metadata yet."""
    component_id: int
    shape: str              # from RecognitionResult.type
    path: List[Point]       # ordered bend vertices
    orientation: Tuple[float, float]   # unit vector of primary axis
    length: float           # total path length (mm)
    bbox: Tuple[float, float, float, float]  # x0,y0,x1,y1
    fingerprint: str
    confidence: float
    evidence: List[dict] = field(default_factory=list)
    recognizer: str = ""


# ─── Phase 9 output ──────────────────────────────────────────────────────────

@dataclass
class AnnotatedBar:
    """Geometry + engineering metadata extracted from annotations."""
    recognized_bar: RecognizedBar
    mark: Optional[str] = None        # "N5"
    diameter: Optional[int] = None    # mm
    spacing: Optional[int] = None     # mm c/c
    notes: str = ""
    annotation_source: str = ""       # "leader" | "mtext_nearest" | "dimension"


# ─── Phase 10 output ─────────────────────────────────────────────────────────

@dataclass
class RebarGroup:
    """Placement information — count tracked with provenance."""
    annotated_bar: AnnotatedBar
    placement_region: Optional[Tuple] = None   # bounding box of the slab zone
    count: int = 0
    count_source: str = "unknown"   # "annotation" | "estimated_from_spacing" | "unknown"
    offset_vector: Tuple[float, float, float] = (0.0, 0.0, 0.0)


# ─── Phase 11 output ─────────────────────────────────────────────────────────

@dataclass
class RebarModel:
    """Actual 3D geometry ready for rendering or export."""
    rebar_group: RebarGroup
    cylinders: List[Any] = field(default_factory=list)   # renderer-specific meshes
    vertices: List[Tuple] = field(default_factory=list)
    triangles: List[Tuple] = field(default_factory=list)
