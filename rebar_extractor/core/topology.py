import uuid
import time
import math
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass, field
from core.context import AnalysisContext
from core.pipeline import PipelineStage
from core.geometry import LineEntity, ArcEntity, PolylineEntity, GeometryEntity
from core.canonical import CanonicalNode
from core.validation import GraphValidator

@dataclass
class GraphEdge:
    geometry_uuid: uuid.UUID
    start_node: int
    end_node: int
    length: float
    angle: float
    curve: bool
    layer: str
    provenance: dict = field(default_factory=dict)

@dataclass
class ConnectedComponent:
    id: int
    nodes: Set[int] = field(default_factory=set)
    edges: List[GraphEdge] = field(default_factory=list)
    # Cache
    edge_count: int = 0
    node_count: int = 0
    # Bbox and centroid calculation can be done lazily or on creation

class TopologyGraph:
    def __init__(self):
        self.edges: List[GraphEdge] = []
        self.node_degrees: Dict[int, int] = {}
        self.adjacency: Dict[int, List[GraphEdge]] = {}
        self.components: List[ConnectedComponent] = []

    def add_edge(self, edge: GraphEdge):
        self.edges.append(edge)
        self.node_degrees[edge.start_node] = self.node_degrees.get(edge.start_node, 0) + 1
        self.node_degrees[edge.end_node] = self.node_degrees.get(edge.end_node, 0) + 1
        
        if edge.start_node not in self.adjacency:
            self.adjacency[edge.start_node] = []
        self.adjacency[edge.start_node].append(edge)
        
        if edge.end_node not in self.adjacency:
            self.adjacency[edge.end_node] = []
        self.adjacency[edge.end_node].append(edge)

class TopologyStage(PipelineStage):
    @property
    def name(self) -> str:
        return "topology"

    def _calc_length(self, p1, p2) -> float:
        return math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
        
    def _calc_angle(self, p1, p2) -> float:
        return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))

    def execute(self, context: AnalysisContext) -> AnalysisContext:
        start_time = time.time()
        
        canonical_nodes = context.canonical_nodes
        repo = context.repository
        
        if not canonical_nodes:
            raise ValueError("Canonical nodes must be built before TopologyGraph")
            
        # Map geometry UUID to canonical nodes that reference it
        # Actually it's easier to map: (geometry_uuid, point_type) -> canonical_node_id
        point_to_node: Dict[Tuple[uuid.UUID, str], int] = {}
        for node in canonical_nodes:
            for ref in node.references:
                point_to_node[ref] = node.id
                
        graph = TopologyGraph()
        
        # Build edges for Lines
        for line in repo.lines.values():
            sn = point_to_node.get((line.id, 'start'))
            en = point_to_node.get((line.id, 'end'))
            if sn and en:
                length = self._calc_length(line.start, line.end)
                angle = self._calc_angle(line.start, line.end)
                edge = GraphEdge(
                    geometry_uuid=line.id, start_node=sn, end_node=en,
                    length=length, angle=angle, curve=False, layer=line.layer,
                    provenance={"source_entity_id": line.source_entity_id}
                )
                graph.add_edge(edge)
                
        # Build edges for Arcs
        for arc in repo.arcs.values():
            sn = point_to_node.get((arc.id, 'start'))
            en = point_to_node.get((arc.id, 'end'))
            if sn and en:
                # Arc length
                span = abs(arc.end_angle - arc.start_angle)
                if span > 360: span -= 360
                length = (span / 360.0) * (2 * math.pi * arc.radius)
                edge = GraphEdge(
                    geometry_uuid=arc.id, start_node=sn, end_node=en,
                    length=length, angle=0.0, curve=True, layer=arc.layer,
                    provenance={"source_entity_id": arc.source_entity_id}
                )
                graph.add_edge(edge)
                
        # Build edges for Polylines (segments)
        for poly in repo.polylines.values():
            num_verts = len(poly.vertices)
            for i in range(num_verts - 1):
                sn = point_to_node.get((poly.id, f'vertex_{i}'))
                en = point_to_node.get((poly.id, f'vertex_{i+1}'))
                if sn and en:
                    length = self._calc_length(poly.vertices[i], poly.vertices[i+1])
                    angle = self._calc_angle(poly.vertices[i], poly.vertices[i+1])
                    edge = GraphEdge(
                        geometry_uuid=poly.id, start_node=sn, end_node=en,
                        length=length, angle=angle, curve=False, layer=poly.layer,
                        provenance={"source_entity_id": poly.source_entity_id}
                    )
                    graph.add_edge(edge)
            if poly.is_closed and num_verts > 2:
                sn = point_to_node.get((poly.id, f'vertex_{num_verts-1}'))
                en = point_to_node.get((poly.id, f'vertex_{0}'))
                if sn and en:
                    length = self._calc_length(poly.vertices[-1], poly.vertices[0])
                    angle = self._calc_angle(poly.vertices[-1], poly.vertices[0])
                    edge = GraphEdge(
                        geometry_uuid=poly.id, start_node=sn, end_node=en,
                        length=length, angle=angle, curve=False, layer=poly.layer,
                        provenance={"source_entity_id": poly.source_entity_id}
                    )
                    graph.add_edge(edge)
                    
        # Apply Node Degrees back to CanonicalNodes for easy inspection
        for node in canonical_nodes:
            # We can dynamically calculate it or store it. Let's just store a degree attribute on CanonicalNode.
            node.degree = graph.node_degrees.get(node.id, 0)
            
        # Graph Validation
        validator = GraphValidator()
        validation_warnings = validator.validate(graph, canonical_nodes)

        # Connected Components Extraction
        visited_nodes = set()
        component_id = 1
        
        for node_id in graph.adjacency.keys():
            if node_id not in visited_nodes:
                comp = ConnectedComponent(id=component_id)
                queue = [node_id]
                visited_edges = set()
                
                while queue:
                    curr = queue.pop(0)
                    if curr in visited_nodes:
                        continue
                    visited_nodes.add(curr)
                    comp.nodes.add(curr)
                    
                    for edge in graph.adjacency.get(curr, []):
                        if id(edge) not in visited_edges:
                            visited_edges.add(id(edge))
                            comp.edges.append(edge)
                            
                            next_node = edge.end_node if edge.start_node == curr else edge.start_node
                            if next_node not in visited_nodes:
                                queue.append(next_node)
                                
                comp.node_count = len(comp.nodes)
                comp.edge_count = len(comp.edges)
                if comp.edge_count > 0:
                    graph.components.append(comp)
                    component_id += 1

        duration = time.time() - start_time
        
        # Update metrics
        context.metrics["graph_edges"] = len(graph.edges)
        context.metrics["connected_components"] = len(graph.components)
        avg_deg = sum(graph.node_degrees.values()) / len(graph.node_degrees) if graph.node_degrees else 0
        context.metrics["average_degree"] = round(avg_deg, 2)
        
        largest = max((c.edge_count for c in graph.components), default=0)
        context.metrics["largest_component"] = largest
        
        new_context = context.evolve(topology=graph)
        self._emit_event(new_context, len(graph.edges), duration, warnings=validation_warnings)
        
        return new_context
