from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any
from uuid import UUID

from core.topology.nodes import CanonicalNode

@dataclass
class GraphEdge:
    id: UUID
    start_node_uuid: UUID
    end_node_uuid: UUID
    geometry_uuid: UUID
    edge_type: str        # 'LINE', 'ARC', 'POLYLINE_SEGMENT'
    length: float
    angle: float
    layer: str
    geometry_hash: str

@dataclass
class ConnectivityGraph:
    nodes: Dict[UUID, CanonicalNode] = field(default_factory=dict)
    edges: Dict[UUID, GraphEdge] = field(default_factory=dict)
    node_to_edges: Dict[UUID, List[UUID]] = field(default_factory=dict)
    edge_to_nodes: Dict[UUID, Tuple[UUID, UUID]] = field(default_factory=dict)

@dataclass
class ConnectedComponent:
    id: UUID
    node_ids: List[UUID]
    edge_ids: List[UUID]
    bbox: Tuple[float, float, float, float]
    statistics: Dict[str, Any]

@dataclass
class ConnectedComponentRepository:
    components: Dict[UUID, ConnectedComponent] = field(default_factory=dict)
