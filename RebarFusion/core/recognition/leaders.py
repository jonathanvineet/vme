"""
Leader Reconstruction.

Turns raw annotation-layer LINE geometry into reconstructed Leader objects
with a true tip (the end pointing at the target, e.g. a rebar) and a true
tail (the end anchored near the annotation text), instead of the previous
approach of treating every raw LINE entity as its own independent 2-point
leader.

Root cause this replaces (see audit_phase08_engineering_association.md):
a leader arrowhead is drawn as 3 connected LINE entities (one shaft + two
short barbs meeting at a point), so "one LINE = one leader" both triples
the leader count and, for the two barb segments, produces a meaningless
pointer tip a few mm from the text rather than the true tip at the target.

Algorithm (deterministic, geometric, not drawing-specific):
  1. Reuse the already-built connectivity graph/components (Phase 6) rather
     than re-reading the DXF.
  2. For each connected component whose edges sit on the leader layer:
       - 3-edge arrowhead pattern (one degree-3 node, three degree-1 nodes):
         the degree-3 node is the tip (all three lines meet at the arrow
         point); the shaft is the longest of the three edges; the tail is
         the shaft's other endpoint (degree-1, away from the barbs).
       - 1-edge simple leader (two degree-1 nodes, no arrowhead drawn):
         lower-confidence fallback — tip/tail cannot be geometrically
         distinguished from the line alone, so both ends are kept and the
         caller (annotation clustering) must disambiguate by proximity to
         text.
       - anything else: not a leader shape, skipped.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from core.topology.graph import ConnectivityGraph, ConnectedComponent, ConnectedComponentRepository


@dataclass
class Leader:
    uuid: UUID
    source_component_uuid: UUID
    layer: str
    shaft_edge_id: UUID
    arrowhead_edge_ids: List[UUID]
    tip: Tuple[float, float, float]     # points at the target (e.g. a bar)
    tail: Tuple[float, float, float]    # anchored near the annotation text
    confidence: float                   # 1.0 = full shaft+arrowhead reconstruction, 0.5 = ambiguous single-line fallback


@dataclass
class LeaderRepository:
    leaders: Dict[UUID, Leader] = field(default_factory=dict)


def _degree(graph: ConnectivityGraph, node_id: UUID) -> int:
    return graph.nodes[node_id].incident_edges


def reconstruct_leaders(graph: ConnectivityGraph, comp_repo: ConnectedComponentRepository,
                         layer: str = "G-ANNO-TEXT") -> LeaderRepository:
    import uuid as _uuid

    repo = LeaderRepository()

    for comp in comp_repo.components.values():
        edges = [graph.edges[e_id] for e_id in comp.edge_ids]
        if not edges or any(e.layer != layer for e in edges):
            continue

        if len(edges) == 3:
            # Arrowhead pattern: exactly one degree-3 node (all three edges
            # meet there = the tip) and three degree-1 nodes (the far ends).
            degree3_nodes = [n for n in comp.node_ids if _degree(graph, n) == 3]
            degree1_nodes = [n for n in comp.node_ids if _degree(graph, n) == 1]
            if len(degree3_nodes) != 1 or len(degree1_nodes) != 3 or len(comp.node_ids) != 4:
                continue

            tip_node = degree3_nodes[0]
            shaft = max(edges, key=lambda e: e.length)
            barbs = [e for e in edges if e.id != shaft.id]
            tail_node = shaft.end_node_uuid if shaft.start_node_uuid == tip_node else shaft.start_node_uuid

            leader = Leader(
                uuid=_uuid.uuid4(),
                source_component_uuid=comp.id,
                layer=layer,
                shaft_edge_id=shaft.id,
                arrowhead_edge_ids=[b.id for b in barbs],
                tip=graph.nodes[tip_node].position,
                tail=graph.nodes[tail_node].position,
                confidence=1.0,
            )
            repo.leaders[leader.uuid] = leader

        elif len(edges) == 1:
            # No arrowhead drawn — can't geometrically tell which end is the
            # tip. Keep both ends available with low confidence; the caller
            # disambiguates by proximity to the annotation text.
            e = edges[0]
            n1, n2 = e.start_node_uuid, e.end_node_uuid
            leader = Leader(
                uuid=_uuid.uuid4(),
                source_component_uuid=comp.id,
                layer=layer,
                shaft_edge_id=e.id,
                arrowhead_edge_ids=[],
                tip=graph.nodes[n2].position,
                tail=graph.nodes[n1].position,
                confidence=0.5,
            )
            repo.leaders[leader.uuid] = leader

        # else: not a recognized leader shape (e.g. text-glyph geometry
        # sharing the annotation layer) — skipped, not forced into a label.

    return repo
