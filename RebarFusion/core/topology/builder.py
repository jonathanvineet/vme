import math
import uuid
from typing import Dict, List, Tuple

from core.geometry.canonical import CanonicalRepository
from core.topology.nodes import CanonicalNodeRepository, CanonicalNode
from core.topology.graph import GraphEdge, ConnectivityGraph, ConnectedComponent, ConnectedComponentRepository
from core.topology.node_builder import node_uuid

NAMESPACE_COMPONENT = uuid.UUID('e29b1390-e555-4ff8-918c-30c800539130')
NAMESPACE_EDGE = uuid.UUID('1c0e3931-1cdb-4e0e-8d8a-83b4b8a2c2cc')

class TopologyBuilder:
    def __init__(self, node_repo: CanonicalNodeRepository, canon_repo: CanonicalRepository):
        self.node_repo = node_repo
        self.canon_repo = canon_repo
        self.graph = ConnectivityGraph()
        self.graph.nodes = self.node_repo.nodes.copy()
        
    def build(self) -> Tuple[ConnectivityGraph, ConnectedComponentRepository, Dict, Dict]:
        self._stage_6_1_build_edges()
        self._stage_6_2_build_adjacency()
        self._stage_6_3_degree_calc()
        
        components = self._stage_6_4_components()
        self._stage_6_5_component_uuids(components)
        
        metrics, comp_repo = self._stage_6_6_metrics(components)
        validation = self._stage_6_7_validation()
        
        return self.graph, comp_repo, metrics, validation

    def _stage_6_1_build_edges(self):
        # Line
        for line in self.canon_repo.lines:
            n1 = node_uuid(*line.start)
            n2 = node_uuid(*line.end)
            if n1 != n2:
                e_id = uuid.uuid5(NAMESPACE_EDGE, str(line.id))
                self.graph.edges[e_id] = GraphEdge(
                    id=e_id, start_node_uuid=n1, end_node_uuid=n2,
                    geometry_uuid=line.id, edge_type='LINE',
                    length=line.length, angle=math.degrees(math.atan2(line.direction[1], line.direction[0])),
                    layer=line.layer, geometry_hash=line.geometry_hash
                )
        
        # Arc
        for arc in self.canon_repo.arcs:
            sa_rad = math.radians(arc.start_angle)
            sx = arc.center[0] + arc.radius * math.cos(sa_rad)
            sy = arc.center[1] + arc.radius * math.sin(sa_rad)
            n1 = node_uuid(sx, sy, 0.0)
            
            ea_rad = math.radians(arc.end_angle)
            ex = arc.center[0] + arc.radius * math.cos(ea_rad)
            ey = arc.center[1] + arc.radius * math.sin(ea_rad)
            n2 = node_uuid(ex, ey, 0.0)
            
            if n1 != n2:
                e_id = uuid.uuid5(NAMESPACE_EDGE, str(arc.id))
                self.graph.edges[e_id] = GraphEdge(
                    id=e_id, start_node_uuid=n1, end_node_uuid=n2,
                    geometry_uuid=arc.id, edge_type='ARC',
                    length=abs(arc.end_angle - arc.start_angle) / 360.0 * 2 * math.pi * arc.radius,
                    angle=arc.start_angle, # simplify
                    layer=arc.layer, geometry_hash=arc.geometry_hash
                )
                
        # Polyline (segmented)
        for poly in self.canon_repo.polylines:
            for i in range(len(poly.vertices) - 1):
                v1 = poly.vertices[i]
                v2 = poly.vertices[i+1]
                n1 = node_uuid(v1[0], v1[1], v1[2] if len(v1)>2 else 0.0)
                n2 = node_uuid(v2[0], v2[1], v2[2] if len(v2)>2 else 0.0)
                
                if n1 != n2:
                    dx = v2[0] - v1[0]
                    dy = v2[1] - v1[1]
                    length = math.hypot(dx, dy)
                    angle = math.degrees(math.atan2(dy, dx))
                    
                    e_id = uuid.uuid5(NAMESPACE_EDGE, f"{poly.id}_{i}")
                    self.graph.edges[e_id] = GraphEdge(
                        id=e_id, start_node_uuid=n1, end_node_uuid=n2,
                        geometry_uuid=poly.id, edge_type='POLYLINE_SEGMENT',
                        length=length, angle=angle,
                        layer=poly.layer, geometry_hash=poly.geometry_hash
                    )
        # Note: CIRCLES are typically single-node closed loops. If we want them as edges, we'd need to link them to themselves, 
        # but the request mentioned "Every edge has exactly two valid nodes" and "No self-loops". We'll skip standalone circles as structural graph edges.

    def _stage_6_2_build_adjacency(self):
        # Initialize
        for n_id in self.graph.nodes:
            self.graph.node_to_edges[n_id] = []
            
        for e_id, edge in self.graph.edges.items():
            self.graph.edge_to_nodes[e_id] = (edge.start_node_uuid, edge.end_node_uuid)
            self.graph.node_to_edges[edge.start_node_uuid].append(e_id)
            self.graph.node_to_edges[edge.end_node_uuid].append(e_id)

    def _stage_6_3_degree_calc(self):
        for n_id, n in self.graph.nodes.items():
            n.incident_edges = len(self.graph.node_to_edges[n_id])

    def _stage_6_4_components(self) -> List[ConnectedComponent]:
        visited_nodes = set()
        components = []
        
        for n_id in self.graph.nodes:
            if n_id in visited_nodes:
                continue
                
            # If a node has no edges, skip component building for it, or it becomes a 1-node component.
            if not self.graph.node_to_edges[n_id]:
                continue
                
            # BFS/DFS
            comp_nodes = []
            comp_edges = set()
            stack = [n_id]
            visited_nodes.add(n_id)
            
            while stack:
                curr = stack.pop()
                comp_nodes.append(curr)
                
                for e_id in self.graph.node_to_edges[curr]:
                    comp_edges.add(e_id)
                    edge = self.graph.edges[e_id]
                    nxt = edge.end_node_uuid if edge.start_node_uuid == curr else edge.start_node_uuid
                    
                    if nxt not in visited_nodes:
                        visited_nodes.add(nxt)
                        stack.append(nxt)
                        
            # Create a temporary component object (UUID assigned next)
            components.append(ConnectedComponent(
                id=uuid.uuid4(), node_ids=comp_nodes, edge_ids=list(comp_edges),
                bbox=(0,0,0,0), statistics={}
            ))
            
        return components

    def _stage_6_5_component_uuids(self, components: List[ConnectedComponent]):
        for comp in components:
            hashes = [self.graph.edges[e_id].geometry_hash for e_id in comp.edge_ids]
            hashes.sort()
            comp.id = uuid.uuid5(NAMESPACE_COMPONENT, "|".join(hashes))

    def _stage_6_6_metrics(self, components: List[ConnectedComponent]) -> Tuple[Dict, ConnectedComponentRepository]:
        comp_repo = ConnectedComponentRepository()
        
        for comp in components:
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = float('-inf'), float('-inf')
            
            total_len = 0.0
            min_len = float('inf')
            max_len = 0.0
            
            for n_id in comp.node_ids:
                pos = self.graph.nodes[n_id].position
                min_x = min(min_x, pos[0])
                min_y = min(min_y, pos[1])
                max_x = max(max_x, pos[0])
                max_y = max(max_y, pos[1])
                
            for e_id in comp.edge_ids:
                l = self.graph.edges[e_id].length
                total_len += l
                min_len = min(min_len, l)
                max_len = max(max_len, l)
                
            comp.bbox = (min_x, min_y, max_x, max_y)
            comp.statistics = {
                "node_count": len(comp.node_ids),
                "edge_count": len(comp.edge_ids),
                "total_length": total_len,
                "longest_edge": max_len,
                "shortest_edge": min_len if min_len != float('inf') else 0.0,
                "average_degree": sum([self.graph.nodes[n].incident_edges for n in comp.node_ids]) / max(1, len(comp.node_ids))
            }
            comp_repo.components[comp.id] = comp
            
        # Graph metrics
        total_nodes = len(self.graph.nodes)
        total_edges = len(self.graph.edges)
        if total_nodes > 0:
            avg_degree = sum([n.incident_edges for n in self.graph.nodes.values()]) / total_nodes
        else:
            avg_degree = 0.0
            
        comp_sizes = [len(c.node_ids) for c in components]
        
        metrics = {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "average_degree": avg_degree,
            "connected_components": len(components),
            "largest_component": max(comp_sizes) if comp_sizes else 0,
            "smallest_component": min(comp_sizes) if comp_sizes else 0,
            "average_component_size": sum(comp_sizes)/len(comp_sizes) if comp_sizes else 0.0
        }
        
        return metrics, comp_repo

    def _stage_6_7_validation(self) -> Dict:
        # Tiered validation: critical (structurally broken graph) and errors
        # (real data-quality defects) both fail the "ready for next phase" gate;
        # warnings/info do not.
        validation = {"critical_errors": [], "errors": [], "warnings": [], "info": []}

        for e_id, edge in self.graph.edges.items():
            if edge.start_node_uuid == edge.end_node_uuid:
                validation["critical_errors"].append(f"Self-loop on edge {e_id}")
            if edge.start_node_uuid not in self.graph.nodes:
                validation["critical_errors"].append(f"Missing start node {edge.start_node_uuid}")
            if edge.end_node_uuid not in self.graph.nodes:
                validation["critical_errors"].append(f"Missing end node {edge.end_node_uuid}")
            if edge.length <= 0.0:
                validation["warnings"].append(f"Zero-length edge {e_id}")

        # Duplicate edges: two edges connecting the same node pair. This can
        # legitimately happen (e.g. an annotation line traced over a rebar
        # line on a different layer), but each occurrence is unresolved
        # duplicate/overlapping source geometry that Phase 3 dedup did not
        # catch, so it's an error requiring an explicit decision, not a
        # silently-ignored warning.
        edge_pairs = set()
        for e_id, edge in self.graph.edges.items():
            pair = tuple(sorted([edge.start_node_uuid, edge.end_node_uuid]))
            if pair in edge_pairs:
                validation["errors"].append(f"Duplicate topological edge between nodes {pair}")
            edge_pairs.add(pair)

        # Orphan nodes (degree 0). ARC centers and CIRCLE centers are
        # registered as nodes (for spatial reference) but are never used as
        # edge endpoints — arcs connect via their start/end angle points, and
        # circles never produce edges at all (see _stage_6_1_build_edges).
        # Degree-0 on one of those points is expected, not a topology defect;
        # degree-0 on any other point (a LINE/POLYLINE endpoint or an ARC
        # start/end point) is a genuine, unexpected orphan.
        non_topological_nodes = set()
        for arc in self.canon_repo.arcs:
            non_topological_nodes.add(node_uuid(arc.center[0], arc.center[1], 0.0))
        for circle in self.canon_repo.circles:
            cz = circle.center[2] if len(circle.center) > 2 else 0.0
            non_topological_nodes.add(node_uuid(circle.center[0], circle.center[1], cz))

        expected_orphans = 0
        unexpected_orphans = []
        for n_id, n in self.graph.nodes.items():
            if n.incident_edges == 0:
                if n_id in non_topological_nodes:
                    expected_orphans += 1
                else:
                    unexpected_orphans.append(n_id)

        if expected_orphans:
            validation["info"].append(
                f"{expected_orphans} orphan nodes are ARC/CIRCLE center reference points (expected, not a topology defect)"
            )
        if unexpected_orphans:
            validation["errors"].append(
                f"{len(unexpected_orphans)} unexpected orphan nodes (degree 0, not an arc/circle center): "
                f"{[str(n) for n in unexpected_orphans[:10]]}"
            )

        return validation
