"""
core/geometry/canonical.py

Canonical geometry dataclasses — the single representation consumed by all
downstream phases (topology, recognition, annotation, model building).

Design principles:
  1. No unresolved transforms. Every coordinate is in world space.
  2. Full provenance preserved from the Phase 2 source entity.
  3. Every entity carries a geometry_hash fingerprint.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID


# ---------------------------------------------------------------------------
# Provenance record — ties a canonical entity back to its Phase 2 source(s)
# ---------------------------------------------------------------------------

@dataclass
class CanonicalProvenance:
    source_entity_uuid: UUID        # Phase 2 GeometryEntity.id
    source_handle: str              # Raw DXF handle
    source_block: Optional[str]     # Block name if exploded from INSERT
    source_reader: str              # e.g. "DXFReader"
    source_drawing: str             # Drawing filename


# ---------------------------------------------------------------------------
# Base canonical entity
# ---------------------------------------------------------------------------

@dataclass
class CanonicalEntity:
    id: UUID
    dxf_type: str                   # Original CAD type (LINE, ARC, …)
    layer: str
    color: int
    linetype: str
    geometry_hash: str              # SHA-256 fingerprint
    bounding_box: Tuple[float, float, float, float]   # (min_x, min_y, max_x, max_y)
    provenance: List[CanonicalProvenance] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Concrete canonical primitives
# ---------------------------------------------------------------------------

@dataclass
class CanonicalLine(CanonicalEntity):
    start: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    end:   Tuple[float, float, float] = (0.0, 0.0, 0.0)
    length: float = 0.0
    direction: Tuple[float, float, float] = (0.0, 0.0, 0.0)   # unit vector


@dataclass
class CanonicalArc(CanonicalEntity):
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 0.0
    start_angle: float = 0.0    # degrees, [0, 360)
    end_angle: float = 0.0      # degrees, [0, 360)
    orientation: str = "CCW"    # "CW" | "CCW"
    midpoint: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class CanonicalCircle(CanonicalEntity):
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 0.0
    area: float = 0.0
    circumference: float = 0.0


@dataclass
class CanonicalPolyline(CanonicalEntity):
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    is_closed: bool = False
    bulges: List[float] = field(default_factory=list)  # one per segment


@dataclass
class CanonicalText(CanonicalEntity):
    text: str = ""
    insertion_point: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    height: float = 0.0
    rotation: float = 0.0


@dataclass
class CanonicalMText(CanonicalEntity):
    text: str = ""
    insertion_point: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    char_height: float = 0.0
    rotation: float = 0.0


@dataclass
class CanonicalDimension(CanonicalEntity):
    text: str = ""
    measurement: float = 0.0
    defpoint: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    p1: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    p2: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class CanonicalHatch(CanonicalEntity):
    pattern_name: str = ""
    solid: bool = False


# ---------------------------------------------------------------------------
# Bounding box levels
# ---------------------------------------------------------------------------

@dataclass
class BoundingBoxReport:
    drawing: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    by_block: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Canonical repository — one per drawing
# ---------------------------------------------------------------------------

@dataclass
class CanonicalRepository:
    """
    The single geometry representation consumed by Phases 4+.
    After canonicalization every INSERT has been exploded, all coordinates
    are in world space, and every entity has a geometry fingerprint.
    """
    drawing_filename: str
    lines:      List[CanonicalLine]      = field(default_factory=list)
    arcs:       List[CanonicalArc]       = field(default_factory=list)
    circles:    List[CanonicalCircle]    = field(default_factory=list)
    polylines:  List[CanonicalPolyline]  = field(default_factory=list)
    texts:      List[CanonicalText]      = field(default_factory=list)
    mtexts:     List[CanonicalMText]     = field(default_factory=list)
    dimensions: List[CanonicalDimension] = field(default_factory=list)
    hatches:    List[CanonicalHatch]     = field(default_factory=list)
    bbox_report: BoundingBoxReport       = field(default_factory=BoundingBoxReport)

    def all_entities(self) -> List[CanonicalEntity]:
        return (self.lines + self.arcs + self.circles + self.polylines +
                self.texts + self.mtexts + self.dimensions + self.hatches)

    def counts(self) -> Dict[str, int]:
        return {
            "LINE":      len(self.lines),
            "ARC":       len(self.arcs),
            "CIRCLE":    len(self.circles),
            "POLYLINE":  len(self.polylines),
            "TEXT":      len(self.texts),
            "MTEXT":     len(self.mtexts),
            "DIMENSION": len(self.dimensions),
            "HATCH":     len(self.hatches),
            "TOTAL":     len(self.all_entities()),
        }
