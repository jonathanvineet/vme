from dataclasses import dataclass, field
from typing import Tuple, List, Dict
from uuid import UUID

@dataclass
class CanonicalNode:
    id: UUID
    position: Tuple[float, float, float]
    connected_entities: List[UUID] = field(default_factory=list)
    incident_edges: int = 0
    source_drawing: str = ""

@dataclass
class CanonicalNodeRepository:
    nodes: Dict[UUID, CanonicalNode] = field(default_factory=dict)
    entity_to_nodes: Dict[UUID, List[UUID]] = field(default_factory=dict)
