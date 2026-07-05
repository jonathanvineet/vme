import uuid
from collections import defaultdict
from typing import Dict, List, Tuple

from core.geometry.canonical import CanonicalRepository
from core.spatial.engine import SpatialQueryEngine
from core.topology.nodes import CanonicalNode, CanonicalNodeRepository

NAMESPACE_NODE = uuid.UUID('f71d5b24-9b57-4638-b7fb-65b1285cb159')

def node_uuid(x: float, y: float, z: float) -> uuid.UUID:
    """Generate a stable UUID5 based on snapped spatial coordinates."""
    # Snapped to 5 decimal places (which aligns with EPSILON=1e-5)
    s = f"{x:.5f},{y:.5f},{z:.5f}"
    return uuid.uuid5(NAMESPACE_NODE, s)

def build_nodes(canon_repo: CanonicalRepository, engine: SpatialQueryEngine, source_drawing: str) -> Tuple[CanonicalNodeRepository, Dict, int]:
    """
    Extract points from Canonical Geometry and build a CanonicalNodeRepository.
    Returns:
        (repo, validation_dict, total_points_extracted)
    """
    repo = CanonicalNodeRepository()
    
    # Track points extracted vs nodes created for metrics
    points_extracted = 0
    
    # Temporary structures to build nodes
    # map: node_uuid -> (x, y, z)
    node_positions: Dict[uuid.UUID, Tuple[float, float, float]] = {}
    # map: node_uuid -> set of entity UUIDs
    node_to_entities = defaultdict(set)
    # map: entity_uuid -> set of node UUIDs
    entity_to_nodes = defaultdict(set)

    def add_point(ent_id: uuid.UUID, pt: Tuple[float, float, ...]):
        nonlocal points_extracted
        points_extracted += 1
        
        x, y = pt[0], pt[1]
        z = pt[2] if len(pt) > 2 else 0.0
        
        n_id = node_uuid(x, y, z)
        if n_id not in node_positions:
            node_positions[n_id] = (x, y, z)
            
        node_to_entities[n_id].add(ent_id)
        entity_to_nodes[ent_id].add(n_id)

    # 1. Extract Points
    for line in canon_repo.lines:
        add_point(line.id, line.start)
        add_point(line.id, line.end)
        
    import math
    for arc in canon_repo.arcs:
        cx, cy = arc.center[0], arc.center[1]
        r = arc.radius
        
        sa_rad = math.radians(arc.start_angle)
        sx = cx + r * math.cos(sa_rad)
        sy = cy + r * math.sin(sa_rad)
        add_point(arc.id, (sx, sy, 0.0))
        
        ea_rad = math.radians(arc.end_angle)
        ex = cx + r * math.cos(ea_rad)
        ey = cy + r * math.sin(ea_rad)
        add_point(arc.id, (ex, ey, 0.0))
        
        add_point(arc.id, arc.center)
        
    for poly in canon_repo.polylines:
        for v in poly.vertices:
            add_point(poly.id, v)
            
    for circle in canon_repo.circles:
        add_point(circle.id, circle.center)

    # 2. Build Repository
    for n_id, pos in node_positions.items():
        ents = list(node_to_entities[n_id])
        node = CanonicalNode(
            id=n_id,
            position=pos,
            connected_entities=ents,
            incident_edges=len(ents),  # temporary degree
            source_drawing=source_drawing
        )
        repo.nodes[n_id] = node

    for e_id, n_ids in entity_to_nodes.items():
        repo.entity_to_nodes[e_id] = list(n_ids)

    # 3. Validation
    validation = {
        "critical_errors": [],
        "warnings": []
    }

    # No Orphan Nodes
    for n_id, node in repo.nodes.items():
        if not node.connected_entities:
            validation["critical_errors"].append(f"Orphan node: {n_id}")

    # Empty Repository
    if not repo.nodes:
        validation["warnings"].append("Node repository is empty (no lines/arcs/polylines/circles)")

    # Missing Entity Links
    # Every geometric primitive (lines, arcs, etc.) should have its points in the repo.
    for e in canon_repo.lines + canon_repo.arcs + canon_repo.polylines + canon_repo.circles:
        if e.id not in repo.entity_to_nodes or not repo.entity_to_nodes[e.id]:
            validation["critical_errors"].append(f"Entity missing node links: {e.id}")

    return repo, validation, points_extracted
