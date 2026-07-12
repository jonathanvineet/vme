"""
Phase 10B — Geometry Recovery.

Recovers a bar's actual centerline from the connectivity graph and
canonical geometry of its representative recognized component, instead of
approximating every bar as a straight line from
`EngineeringFamily.length`/`orientation` (the root cause identified in
docs/audits/phase10/10.0_reconstruction_audit.md). Curved edges (ARC) are
sampled into multiple points so bends are preserved as real geometry, not
summarized away into a single length+direction pair.

Topology cases, by leaf count within the component:
  - 2 leaves (straight_bar, l_bar, u_bar): walk the simple path between
    them, in geometry order.
  - 0 leaves, all degree 2 (stirrup): walk the closed loop.
  - >2 leaves or any degree>=3 node (branch): no single unambiguous bar
    path exists. Recovers the longest leaf-to-leaf path by total edge
    length as the primary bar and marks `truncated_branch=True` with the
    excluded edge count, rather than silently picking one arbitrary arm
    and pretending the branch was fully represented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from uuid import UUID

Point3D = Tuple[float, float, float]

ARC_SAMPLE_SEGMENTS = 8


@dataclass
class RecoveredPath:
    points: List[Point3D]
    closed: bool
    truncated_branch: bool
    excluded_edge_count: int
    method: str  # 'simple_path' | 'closed_loop' | 'longest_path_in_branch' | 'fallback_straight'
    confidence: float = 1.0
    notes: List[str] = field(default_factory=list)


def _arc_endpoint_positions(entity) -> Tuple[Point3D, Point3D]:
    cx, cy, cz = entity.center
    r = entity.radius
    s = math.radians(entity.start_angle)
    e = math.radians(entity.end_angle)
    return (
        (cx + r * math.cos(s), cy + r * math.sin(s), cz),
        (cx + r * math.cos(e), cy + r * math.sin(e), cz),
    )


def _sample_arc(entity, from_pos: Point3D, n: int = ARC_SAMPLE_SEGMENTS) -> List[Point3D]:
    """Points along the arc from from_pos to the other endpoint, inclusive, in that direction."""
    s_pos, e_pos = _arc_endpoint_positions(entity)

    def close(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-2

    forward = close(from_pos, s_pos)
    a0, a1 = entity.start_angle, entity.end_angle
    sweep = (a1 - a0) % 360.0
    if entity.orientation == "CW":
        sweep -= 360.0
    if not forward:
        a0, a1 = a1, a0
        sweep = -sweep

    cx, cy, cz = entity.center
    r = entity.radius
    points = []
    for i in range(n + 1):
        t = i / n
        ang = math.radians(a0 + sweep * t)
        points.append((cx + r * math.cos(ang), cy + r * math.sin(ang), cz))
    return points


def _edge_points(edge, entity, from_pos: Point3D, to_pos: Point3D) -> List[Point3D]:
    """Points tracing this edge from from_pos to to_pos (both included), excluding from_pos
    (the caller already has it from the previous edge) so segments concatenate cleanly."""
    if edge.edge_type == "ARC" and entity is not None:
        pts = _sample_arc(entity, from_pos)
        return pts[1:]  # drop duplicate from_pos
    # LINE / POLYLINE_SEGMENT / unknown: graph node positions are authoritative endpoints.
    return [to_pos]


def _local_adjacency(component, graph) -> Dict[UUID, List[Tuple[UUID, UUID]]]:
    """node_id -> [(edge_id, other_node_id), ...], restricted to this component's own edges."""
    adjacency: Dict[UUID, List[Tuple[UUID, UUID]]] = {n: [] for n in component.node_ids}
    for e_id in component.edge_ids:
        edge = graph.edges.get(e_id)
        if not edge:
            continue
        a, b = edge.start_node_uuid, edge.end_node_uuid
        adjacency.setdefault(a, []).append((e_id, b))
        adjacency.setdefault(b, []).append((e_id, a))
    return adjacency


def _walk(node_sequence: List[UUID], edge_sequence: List[UUID], graph, entity_by_geom_id: Dict) -> List[Point3D]:
    points = [graph.nodes[node_sequence[0]].position]
    for i, e_id in enumerate(edge_sequence):
        edge = graph.edges[e_id]
        to_node = node_sequence[i + 1]
        to_pos = graph.nodes[to_node].position
        entity = entity_by_geom_id.get(edge.geometry_uuid)
        points.extend(_edge_points(edge, entity, points[-1], to_pos))
    return points


def _longest_leaf_to_leaf_path(leaves: List[UUID], adjacency, graph) -> Tuple[List[UUID], List[UUID], int]:
    """BFS from every leaf; return the (node_seq, edge_seq) of the pair with
    the greatest total edge length, plus how many component edges were not used."""
    best = None
    all_used_edges = set()
    for start in leaves:
        # BFS tracking path (nodes, edges, cumulative length) to every reachable node.
        visited = {start: ([start], [], 0.0)}
        queue = [start]
        while queue:
            curr = queue.pop(0)
            nodes, edges, length = visited[curr]
            for e_id, nxt in adjacency.get(curr, []):
                if nxt in visited:
                    continue
                edge = graph.edges[e_id]
                visited[nxt] = (nodes + [nxt], edges + [e_id], length + edge.length)
                queue.append(nxt)
        for leaf in leaves:
            if leaf == start or leaf not in visited:
                continue
            nodes, edges, length = visited[leaf]
            if best is None or length > best[2]:
                best = (nodes, edges, length)

    if best is None:
        return [], [], 0
    return best[0], best[1], 0  # excluded-edge count is computed by the caller


def recover_bar_path(component, graph, entity_by_geom_id: Dict) -> RecoveredPath:
    adjacency = _local_adjacency(component, graph)
    degree = {n: len(edges) for n, edges in adjacency.items()}
    leaves = [n for n, d in degree.items() if d == 1]
    branch_nodes = [n for n, d in degree.items() if d >= 3]

    total_edges = len(component.edge_ids)

    if not branch_nodes and len(leaves) == 2:
        # Simple path: walk from one leaf to the other.
        start, goal = leaves[0], leaves[1]
        node_seq, edge_seq = _bfs_path(start, goal, adjacency)
        points = _walk(node_seq, edge_seq, graph, entity_by_geom_id)
        return RecoveredPath(points=points, closed=False, truncated_branch=False,
                              excluded_edge_count=0, method="simple_path",
                              confidence=1.0, notes=["Full simple path recovered, no edges excluded."])

    if not leaves and not branch_nodes and component.node_ids:
        # Closed loop: every node degree 2 (stirrup).
        start = component.node_ids[0]
        first_edge_id, next_node = adjacency[start][0]
        node_seq = [start, next_node]
        edge_seq = [first_edge_id]
        prev = start
        curr = next_node
        while curr != start:
            options = [(e, n) for e, n in adjacency[curr] if not (e == edge_seq[-1])]
            e_id, nxt = options[0]
            edge_seq.append(e_id)
            node_seq.append(nxt)
            prev, curr = curr, nxt
            if len(edge_seq) > total_edges + 1:
                break  # safety valve against a malformed graph
        points = _walk(node_seq, edge_seq, graph, entity_by_geom_id)
        return RecoveredPath(points=points, closed=True, truncated_branch=False,
                              excluded_edge_count=0, method="closed_loop",
                              confidence=1.0, notes=["Full closed loop recovered, no edges excluded."])

    if leaves:
        # Branch: no single path represents the whole shape. Recover the
        # longest leaf-to-leaf path as the primary bar; document the rest
        # as excluded rather than silently dropping it.
        node_seq, edge_seq, _ = _longest_leaf_to_leaf_path(leaves, adjacency, graph)
        if node_seq:
            points = _walk(node_seq, edge_seq, graph, entity_by_geom_id)
            excluded = max(0, total_edges - len(edge_seq))
            confidence = round(len(edge_seq) / total_edges, 3) if total_edges else 0.5
            notes = [f"Component has a branch/junction node; recovered the longest leaf-to-leaf "
                     f"path ({len(edge_seq)}/{total_edges} edges). {excluded} edge(s) excluded, "
                     f"not represented in this bar's geometry."]
            return RecoveredPath(points=points, closed=False, truncated_branch=True,
                                  excluded_edge_count=excluded, method="longest_path_in_branch",
                                  confidence=confidence, notes=notes)

    # No recoverable topology (e.g. a single isolated edge with degree-0
    # endpoints, or an empty component) -- fall back to node positions.
    positions = [graph.nodes[n].position for n in component.node_ids]
    return RecoveredPath(points=positions, closed=False, truncated_branch=bool(branch_nodes),
                          excluded_edge_count=max(0, total_edges - max(0, len(positions) - 1)),
                          method="fallback_straight", confidence=0.5,
                          notes=["No recoverable path topology; fell back to raw node positions."])


def _bfs_path(start: UUID, goal: UUID, adjacency) -> Tuple[List[UUID], List[UUID]]:
    visited = {start: ([start], [])}
    queue = [start]
    while queue:
        curr = queue.pop(0)
        if curr == goal:
            return visited[curr]
        nodes, edges = visited[curr]
        for e_id, nxt in adjacency.get(curr, []):
            if nxt in visited:
                continue
            visited[nxt] = (nodes + [nxt], edges + [e_id])
            queue.append(nxt)
    return visited.get(goal, ([start], []))
