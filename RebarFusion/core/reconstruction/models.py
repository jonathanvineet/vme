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
