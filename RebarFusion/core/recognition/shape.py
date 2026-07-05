"""
core/recognition.py

ShapeRecognizerRegistry + individual recognizers.

Classification order per component:
    1. Open / Closed topology
    2. Node Degree Pattern  (e.g. [1,2,2,1])
    3. Turn Sequence        (bend angles)
    4. Fingerprint          (compact string)

Every recognizer returns a RecognitionResult. The registry picks the one
with the highest confidence. Unknown/no match → confidence 0.0, type "unknown".
"""

from __future__ import annotations
import math
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Any

from core.engineering.objects import RecognitionResult, RecognizedBar
from core.topology.graph import ConnectedComponent, TopologyGraph
from core.topology.canonical import CanonicalNode
from core.geometry.entities import Point
from core.context import AnalysisContext
from core.pipeline import PipelineStage


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _walk_chain(comp: ConnectedComponent, graph: TopologyGraph,
                node_map: Dict[int, CanonicalNode]) -> List[Point]:
    """
    Walk an open or closed chain of edges in order, returning ordered Point path.
    Starts from a degree-1 node if the chain is open.
    """
    # Find start node: prefer degree-1 (endpoint) for open chains
    start = None
    for nid in comp.nodes:
        if graph.node_degrees.get(nid, 0) == 1:
            start = nid
            break
    if start is None:
        # closed chain — pick arbitrary first node
        start = next(iter(comp.nodes))

    visited_edges = set()
    path_nodes = [start]
    current = start

    while True:
        moved = False
        for edge in graph.adjacency.get(current, []):
            if id(edge) in visited_edges:
                continue
            if edge.geometry_uuid not in {e.geometry_uuid for e in comp.edges}:
                continue
            visited_edges.add(id(edge))
            next_node = edge.end_node if edge.start_node == current else edge.start_node
            path_nodes.append(next_node)
            current = next_node
            moved = True
            break
        if not moved:
            break

    pts = []
    for nid in path_nodes:
        n = node_map.get(nid)
        if n:
            pts.append(n.point)
    return pts


def _path_length(path: List[Point]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        dx = path[i+1].x - path[i].x
        dy = path[i+1].y - path[i].y
        total += math.sqrt(dx*dx + dy*dy)
    return total


def _turn_angles(path: List[Point]) -> List[float]:
    """Return interior turn angles (degrees) at each midpoint of the path."""
    angles = []
    for i in range(1, len(path) - 1):
        a = path[i-1]
        b = path[i]
        c = path[i+1]
        v1 = (b.x - a.x, b.y - a.y)
        v2 = (c.x - b.x, c.y - b.y)
        mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
        mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
        if mag1 < 1e-6 or mag2 < 1e-6:
            continue
        dot = (v1[0]*v2[0] + v1[1]*v2[1]) / (mag1 * mag2)
        dot = max(-1.0, min(1.0, dot))
        angle = math.degrees(math.acos(dot))
        angles.append(round(angle, 1))
    return angles


def _orientation(path: List[Point]) -> Tuple[float, float]:
    """Primary axis unit vector from first to last point."""
    if len(path) < 2:
        return (1.0, 0.0)
    dx = path[-1].x - path[0].x
    dy = path[-1].y - path[0].y
    mag = math.sqrt(dx*dx + dy*dy)
    if mag < 1e-9:
        return (1.0, 0.0)
    return (dx/mag, dy/mag)


def _bbox(path: List[Point]) -> Tuple[float,float,float,float]:
    xs = [p.x for p in path]
    ys = [p.y for p in path]
    return min(xs), min(ys), max(xs), max(ys)


def _build_fingerprint(comp: ConnectedComponent, graph: TopologyGraph,
                        path: List[Point], is_closed: bool) -> str:
    """L{lines}-A{arcs}-V{vertices}-{length:.0f}-{'C' if closed else 'O'}"""
    lines = sum(1 for e in comp.edges if not e.curve)
    arcs  = sum(1 for e in comp.edges if e.curve)
    length = _path_length(path)
    closure = "C" if is_closed else "O"
    return f"L{lines}-A{arcs}-V{len(path)}-{length:.0f}-{closure}"


def _is_closed(comp: ConnectedComponent, graph: TopologyGraph) -> bool:
    """True if every node in the component has degree >= 2."""
    return all(graph.node_degrees.get(nid, 0) >= 2 for nid in comp.nodes)


def _degree_sequence(comp: ConnectedComponent, graph: TopologyGraph) -> List[int]:
    return sorted([graph.node_degrees.get(nid, 0) for nid in comp.nodes])


def _slenderness(bbox: Tuple) -> float:
    """Max(W,H) / Min(W,H) — high means long and thin like a bar."""
    x0,y0,x1,y1 = bbox
    w = max(x1-x0, 1.0)
    h = max(y1-y0, 1.0)
    return max(w,h) / min(w,h)


# ─── Base Recognizer ─────────────────────────────────────────────────────────

class BaseRecognizer(ABC):
    MIN_LENGTH = 80.0          # mm — shorter than this → likely noise

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def recognize(self, comp: ConnectedComponent, graph: TopologyGraph,
                  node_map: Dict[int, CanonicalNode]) -> Optional[RecognitionResult]: ...


# ─── Recognizers ─────────────────────────────────────────────────────────────

class StraightBarRecognizer(BaseRecognizer):
    """Exactly 2 nodes (degree 1 each) connected by 1+ collinear edges, no arcs."""
    @property
    def name(self): return "StraightBarRecognizer"

    def recognize(self, comp, graph, node_map):
        if _is_closed(comp, graph):
            return None
        if any(e.curve for e in comp.edges):
            return None

        path = _walk_chain(comp, graph, node_map)
        if len(path) < 2:
            return None
        length = _path_length(path)
        if length < self.MIN_LENGTH:
            return None

        # All turns should be near 180° (straight)
        turns = _turn_angles(path)
        if any(abs(t - 180.0) > 25.0 for t in turns):
            return None

        slend = _slenderness(_bbox(path))
        conf = 0.50 + min(0.40, slend / 50.0)   # longer/thinner → higher confidence

        return RecognitionResult(
            type="straight_bar", confidence=round(conf, 3),
            fingerprint=_build_fingerprint(comp, graph, path, False),
            reason=f"2-node open chain, no arcs, slenderness {slend:.1f}",
            recognizer=self.name, geometry=comp
        )


class LBarRecognizer(BaseRecognizer):
    """Open chain with exactly one ~90° bend."""
    @property
    def name(self): return "LBarRecognizer"

    def recognize(self, comp, graph, node_map):
        if _is_closed(comp, graph):
            return None
        path = _walk_chain(comp, graph, node_map)
        if len(path) < 3:
            return None
        length = _path_length(path)
        if length < self.MIN_LENGTH:
            return None

        turns = _turn_angles(path)
        right_angle_turns = [t for t in turns if abs(t - 90.0) < 20.0]
        non_straight = [t for t in turns if abs(t - 180.0) > 25.0]

        if len(right_angle_turns) != 1 or len(non_straight) != 1:
            return None

        return RecognitionResult(
            type="l_bar", confidence=0.82,
            fingerprint=_build_fingerprint(comp, graph, path, False),
            reason=f"Open chain, 1 right-angle bend at {right_angle_turns[0]:.0f}°",
            recognizer=self.name, geometry=comp
        )


class UBarRecognizer(BaseRecognizer):
    """Open chain with exactly two ~90° bends (U shape)."""
    @property
    def name(self): return "UBarRecognizer"

    def recognize(self, comp, graph, node_map):
        if _is_closed(comp, graph):
            return None
        path = _walk_chain(comp, graph, node_map)
        if len(path) < 4:
            return None
        length = _path_length(path)
        if length < self.MIN_LENGTH:
            return None

        turns = _turn_angles(path)
        right_angle_turns = [t for t in turns if abs(t - 90.0) < 20.0]
        non_straight = [t for t in turns if abs(t - 180.0) > 25.0]

        if len(right_angle_turns) != 2 or len(non_straight) != 2:
            return None

        return RecognitionResult(
            type="u_bar", confidence=0.80,
            fingerprint=_build_fingerprint(comp, graph, path, False),
            reason=f"Open chain, 2 right-angle bends",
            recognizer=self.name, geometry=comp
        )


class ClosedShapeRecognizer(BaseRecognizer):
    """Closed loop → stirrup or mesh. Must have 4+ nodes."""
    @property
    def name(self): return "ClosedShapeRecognizer"

    def recognize(self, comp, graph, node_map):
        if not _is_closed(comp, graph):
            return None
        if len(comp.nodes) < 4:
            return None

        path = _walk_chain(comp, graph, node_map)
        length = _path_length(path)
        if length < self.MIN_LENGTH:
            return None

        return RecognitionResult(
            type="stirrup", confidence=0.78,
            fingerprint=_build_fingerprint(comp, graph, path, True),
            reason=f"Closed loop, {comp.node_count} nodes, {comp.edge_count} edges",
            recognizer=self.name, geometry=comp
        )


class DimensionLeaderRecognizer(BaseRecognizer):
    """
    Heuristic: very short total length OR extreme aspect ratio (almost zero height)
    → likely a dimension line or leader, not a bar.
    """
    @property
    def name(self): return "DimensionLeaderRecognizer"

    def recognize(self, comp, graph, node_map):
        path = _walk_chain(comp, graph, node_map)
        if not path:
            return None

        length = _path_length(path)
        x0,y0,x1,y1 = _bbox(path)
        w = x1-x0
        h = y1-y0
        thickness = min(w, h)

        # Dimension lines are often a single segment with very small height
        if len(comp.edges) <= 2 and thickness < 50.0 and length < 500.0:
            return RecognitionResult(
                type="dimension", confidence=0.70,
                fingerprint=_build_fingerprint(comp, graph, path, False),
                reason=f"Short ({length:.0f}mm), thin ({thickness:.0f}mm) → likely dimension",
                recognizer=self.name, geometry=comp
            )
        return None


class SymbolRecognizer(BaseRecognizer):
    """
    Small closed polygons (length < 80mm) — rebar end-cap symbols,
    section markers, or detail circles. Not structural geometry.
    """
    @property
    def name(self): return "SymbolRecognizer"

    def recognize(self, comp, graph, node_map):
        if not _is_closed(comp, graph):
            return None
        path = _walk_chain(comp, graph, node_map)
        length = _path_length(path)
        if length > 120.0:  # too large to be a symbol
            return None
        return RecognitionResult(
            type="symbol", confidence=0.75,
            fingerprint=_build_fingerprint(comp, graph, path, True),
            reason=f"Small closed polygon, length={length:.0f}mm → end-cap symbol",
            recognizer=self.name, geometry=comp
        )


class BranchRecognizer(BaseRecognizer):
    """
    Components with at least one degree-3+ node — T-junctions or
    bars with hooks. Classified as 'branch' for further analysis.
    """
    @property
    def name(self): return "BranchRecognizer"

    def recognize(self, comp, graph, node_map):
        if _is_closed(comp, graph):
            return None
        has_branch = any(graph.node_degrees.get(nid, 0) >= 3 for nid in comp.nodes)
        if not has_branch:
            return None
        path = _walk_chain(comp, graph, node_map)
        length = _path_length(path)
        if length < self.MIN_LENGTH:
            return None
        return RecognitionResult(
            type="branch", confidence=0.60,
            fingerprint=_build_fingerprint(comp, graph, path, False),
            reason=f"Contains degree-3+ node — T-junction or hooked bar",
            recognizer=self.name, geometry=comp
        )


class CompoundRecognizer(BaseRecognizer):
    """
    Very large components (> 5000mm, many nodes, low slenderness) —
    likely slab outlines, grid lines, or section frames, not bars.
    """
    @property
    def name(self): return "CompoundRecognizer"

    def recognize(self, comp, graph, node_map):
        if comp.edge_count < 4:
            return None
        path = _walk_chain(comp, graph, node_map)
        length = _path_length(path)
        if length < 5000.0:
            return None
        slend = _slenderness(_bbox(path)) if path else 0
        if slend > 10.0:  # still slender → could be a long bar — don't label it 'outline'
            return None
        return RecognitionResult(
            type="structural_outline", confidence=0.65,
            fingerprint=_build_fingerprint(comp, graph, path, _is_closed(comp, graph)),
            reason=f"Large ({length:.0f}mm), low slenderness ({slend:.1f}) → slab/frame outline",
            recognizer=self.name, geometry=comp
        )


class UnknownRecognizer(BaseRecognizer):
    """Catch-all — always returns 'unknown' at confidence 0.1."""
    @property
    def name(self): return "UnknownRecognizer"

    def recognize(self, comp, graph, node_map):
        path = _walk_chain(comp, graph, node_map)
        return RecognitionResult(
            type="unknown", confidence=0.10,
            fingerprint=_build_fingerprint(comp, graph, path, _is_closed(comp, graph)),
            reason="No recognizer matched",
            recognizer=self.name, geometry=comp
        )


# ─── Registry ────────────────────────────────────────────────────────────────

class ShapeRecognizerRegistry:
    """
    Runs all recognizers on a component. Returns the highest-confidence result.
    UnknownRecognizer is always last and always matches.
    """
    def __init__(self):
        self._recognizers: List[BaseRecognizer] = [
            CompoundRecognizer(),      # classify large outlines first
            SymbolRecognizer(),         # then tiny symbols
            StraightBarRecognizer(),
            LBarRecognizer(),
            UBarRecognizer(),
            ClosedShapeRecognizer(),
            BranchRecognizer(),         # T-junctions after specific shapes
            DimensionLeaderRecognizer(),
            UnknownRecognizer(),
        ]

    def register(self, recognizer: BaseRecognizer):
        # Insert before UnknownRecognizer
        self._recognizers.insert(-1, recognizer)

    def recognize(self, comp: ConnectedComponent, graph: TopologyGraph,
                  node_map: Dict[int, CanonicalNode]) -> RecognitionResult:
        best: Optional[RecognitionResult] = None
        for rec in self._recognizers:
            result = rec.recognize(comp, graph, node_map)
            if result and (best is None or result.confidence > best.confidence):
                best = result
            if best and best.confidence >= 0.95:
                break  # good enough — stop early
        return best


# ─── Pipeline Stage ──────────────────────────────────────────────────────────

class ShapeRecognitionStage(PipelineStage):
    @property
    def name(self): return "shape_recognition"

    def execute(self, context: AnalysisContext) -> AnalysisContext:
        start = time.time()

        graph = context.topology
        canonical_nodes = context.canonical_nodes

        if not graph or not canonical_nodes:
            raise ValueError("Topology and canonical nodes are required before ShapeRecognitionStage")

        node_map = {n.id: n for n in canonical_nodes}
        registry = ShapeRecognizerRegistry()

        results: List[RecognitionResult] = []
        recognized_bars: List[RecognizedBar] = []

        type_counts: Dict[str, int] = {}

        for comp in graph.components:
            result = registry.recognize(comp, graph, node_map)
            results.append(result)
            type_counts[result.type] = type_counts.get(result.type, 0) + 1

            # Build RecognizedBar for anything that looks like a bar
            if result.type in ("straight_bar", "l_bar", "u_bar", "stirrup"):
                path = _walk_chain(comp, graph, node_map)
                rb = RecognizedBar(
                    component_id=comp.id,
                    shape=result.type,
                    path=path,
                    orientation=_orientation(path),
                    length=_path_length(path),
                    bbox=_bbox(path) if path else (0,0,0,0),
                    fingerprint=result.fingerprint,
                    confidence=result.confidence,
                    evidence=[{"recognizer": result.recognizer, "reason": result.reason}],
                    recognizer=result.recognizer
                )
                recognized_bars.append(rb)

        duration = time.time() - start

        # Store in context metrics for downstream stages
        new_context = context.evolve()
        new_context.metrics["recognition_results"] = results
        new_context.metrics["recognized_bars"] = recognized_bars
        new_context.metrics["recognition_type_counts"] = type_counts

        total_bars = len(recognized_bars)
        self._emit_event(new_context, total_bars, duration)
        return new_context
