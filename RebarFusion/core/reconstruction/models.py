from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple
from uuid import UUID


Point3D = Tuple[float, float, float]
Vector3D = Tuple[float, float, float]


@dataclass
class BoundingBox:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float


@dataclass
class CoordinateFrame:
    origin: Point3D
    u_axis: Vector3D
    v_axis: Vector3D
    w_axis: Vector3D
    thickness: float = 0.0
    cover: float = 40.0


@dataclass
class BarBend:
    vertex: Point3D
    angle_degrees: float
    radius: float


@dataclass
class BarHook:
    end: str
    angle_degrees: float
    length: float


@dataclass
class BarPath:
    uuid: UUID
    family_uuid: UUID
    member_uuid: UUID
    points: List[Point3D]
    bends: List[BarBend] = field(default_factory=list)
    hooks: List[BarHook] = field(default_factory=list)
    closed: bool = False
    # Phase 10B geometry recovery provenance (see core/reconstruction/geometry_recovery.py):
    # recovery_method records how this path was derived ('simple_path',
    # 'closed_loop', 'longest_path_in_branch', or 'fallback_straight'), and
    # truncated_branch/excluded_edge_count are set honestly when the source
    # component was a branch/junction shape with no single unambiguous bar
    # path -- the longest leaf-to-leaf path is kept, the rest is not
    # silently discarded without a record of it.
    recovery_method: str = "unknown"
    truncated_branch: bool = False
    excluded_edge_count: int = 0
    # recovery_confidence is deliberately independent of engineering
    # confidence (EngineeringFamily.confidence / PhysicalBar.confidence,
    # which reflect annotation/association/spacing trust). This answers a
    # different question: how faithfully was the GEOMETRY recovered from
    # the component, regardless of whether the engineering data attached to
    # it is trustworthy. 1.0 for simple_path/closed_loop (nothing
    # excluded), proportional to edges_used/total_edges for a truncated
    # branch, 0.5 for the straight-line fallback (no real recovery at all).
    recovery_confidence: float = 1.0
    recovery_notes: List[str] = field(default_factory=list)


@dataclass
class AssemblyLayer:
    uuid: UUID
    name: str
    direction: str
    family_uuids: List[UUID]
    bar_uuids: List[UUID] = field(default_factory=list)
    z_offset: float = 0.0


@dataclass
class PhysicalBar:
    uuid: UUID
    family_uuid: UUID
    member_uuid: UUID
    mark: str
    diameter: float
    radius: float
    centerline: BarPath
    path: List[Point3D]
    bar_type: str
    layer_uuid: Optional[UUID]
    adjustment_notes: List[str]
    confidence: float
    # Never fabricate engineering data silently (see
    # docs/audits/phase10/10.0_reconstruction_audit.md, 10F finding):
    # diameter_source is 'annotation' when `diameter` came from real Phase 8
    # association data, or 'missing_visual_fallback' when no diameter data
    # existed and `diameter` is only a nominal value for mesh visualization.
    # diameter_confidence is 1.0 for a real annotation-backed value, 0.0 for
    # the fallback -- a viewer/consumer should never treat these the same.
    diameter_source: str = "annotation"
    diameter_confidence: float = 1.0


@dataclass
class ReinforcementAssembly:
    uuid: UUID
    assembly_type: str
    families: List[Any]
    local_coordinate_system: CoordinateFrame
    bounding_box: BoundingBox
    confidence: float
    layers: List[AssemblyLayer] = field(default_factory=list)
    bars: List[PhysicalBar] = field(default_factory=list)


@dataclass
class ReconstructionMesh:
    uuid: UUID
    assembly_uuid: UUID
    bar_uuid: UUID
    vertices: List[Point3D]
    faces: List[Tuple[int, int, int]]
    confidence: float
