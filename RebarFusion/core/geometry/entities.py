import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple, Dict
from uuid import UUID

@dataclass
class Point:
    x: float
    y: float
    z: float = 0.0

@dataclass
class Matrix44:
    """4x4 Transformation Matrix"""
    m: List[float] = field(default_factory=lambda: [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
    ])

@dataclass
class GeometryEntity:
    """Extreme provenance base class for all translated CAD geometry."""
    id: UUID
    dxf_type: str
    layer: str
    color: int
    linetype: str
    handle: str
    owner_handle: str
    parent_block: Optional[str]
    transform: Matrix44
    bounding_box: Tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
    raw_properties: Dict[str, Any]

@dataclass
class LineEntity(GeometryEntity):
    start: Point
    end: Point

@dataclass
class ArcEntity(GeometryEntity):
    center: Point
    radius: float
    start_angle: float  # degrees
    end_angle: float    # degrees

@dataclass
class PolylineEntity(GeometryEntity):
    vertices: List[Point]
    is_closed: bool

@dataclass
class InsertEntity(GeometryEntity):
    block_name: str
    insertion_point: Point
    rotation: float     # degrees
    scale_x: float
    scale_y: float
    scale_z: float

@dataclass
class TextEntity(GeometryEntity):
    text: str
    insertion_point: Point
    height: float
    rotation: float

@dataclass
class MTextEntity(GeometryEntity):
    text: str
    insertion_point: Point
    char_height: float
    rotation: float

@dataclass
class DimensionEntity(GeometryEntity):
    text: str
    measurement: float
    defpoint: Point      # usually insertion/text position
    p1: Point           # extension line 1 origin
    p2: Point           # extension line 2 origin
    
@dataclass
class HatchEntity(GeometryEntity):
    pattern_name: str
    solid: bool
    paths: List[Any]    # Boundary paths
    
@dataclass
class CircleEntity(GeometryEntity):
    center: Point
    radius: float

@dataclass
class UnknownEntity(GeometryEntity):
    dxf_type: str       # Redundant with base class but explicit
    raw_data: str       # basic string dump
