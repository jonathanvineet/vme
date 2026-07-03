from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any

@dataclass
class Point:
    x: float
    y: float
    z: float = 0.0
    
    def as_tuple(self):
        return (self.x, self.y, self.z)

@dataclass
class GeometryEntity:
    """Base class for all unified geometry entities."""
    layer: str
    color: int

@dataclass
class LineEntity(GeometryEntity):
    start: Point
    end: Point

@dataclass
class ArcEntity(GeometryEntity):
    center: Point
    radius: float
    start_angle: float
    end_angle: float

@dataclass
class PolylineEntity(GeometryEntity):
    vertices: List[Point]
    is_closed: bool = False

@dataclass
class BlockReference(GeometryEntity):
    name: str
    insert: Point
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    scale_z: float = 1.0
    entities: List[GeometryEntity] = field(default_factory=list)

@dataclass
class TextEntity(GeometryEntity):
    insert: Point
    text: str
    height: float = 1.0

@dataclass
class DimensionEntity(GeometryEntity):
    defpoint: Point
    text_midpoint: Point
    measurement: float
    text: str = ""
