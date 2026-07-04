import uuid
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any, Dict

@dataclass
class Point:
    x: float
    y: float
    z: float = 0.0
    
    def as_tuple(self):
        return (self.x, self.y, self.z)

@dataclass(kw_only=True)
class GeometryEntity:
    """Base class for all unified geometry entities."""
    id: uuid.UUID
    layer: str
    color: int
    
    # Provenance
    source_entity_id: Optional[str] = None
    source_block: Optional[str] = None
    source_layer: Optional[str] = None
    transform_stack: List[Any] = field(default_factory=list)
    parent_block: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(kw_only=True)
class LineEntity(GeometryEntity):
    start: Point
    end: Point

@dataclass(kw_only=True)
class ArcEntity(GeometryEntity):
    center: Point
    radius: float
    start_angle: float
    end_angle: float

@dataclass(kw_only=True)
class PolylineEntity(GeometryEntity):
    vertices: List[Point]
    is_closed: bool = False

@dataclass(kw_only=True)
class BlockReference(GeometryEntity):
    name: str
    insert: Point
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    scale_z: float = 1.0
    # The sub-entities "owned" by this block
    children: List[uuid.UUID] = field(default_factory=list)

@dataclass(kw_only=True)
class TextEntity(GeometryEntity):
    insert: Point
    text: str
    height: float = 1.0

@dataclass(kw_only=True)
class DimensionEntity(GeometryEntity):
    defpoint: Point
    text_midpoint: Point
    measurement: float
    text: str = ""
