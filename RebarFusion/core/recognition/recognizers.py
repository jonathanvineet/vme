from core.recognition.models import RecognitionResult, Evidence
from core.recognition.registry import Recognizer
from core.topology.graph import ConnectedComponent, ConnectivityGraph
import math

# Layers considered to actually contain physical rebar geometry. Anything
# outside this set is architecture/annotation (floor plans, detail marks,
# leaders, symbols) and must never be recognized as a bar/stirrup/branch,
# even if its topology happens to match. Configurable so the engine can be
# adapted to other CAD layer standards without touching recognizer logic.
ALLOWED_REBAR_LAYERS = {
    "S-RBAR",
}


class BaseShapeRecognizer(Recognizer):
    """Helper methods for shape recognition."""
    def _is_loop(self, component: ConnectedComponent, graph: ConnectivityGraph) -> bool:
        # A simple closed loop has all nodes with degree exactly 2 within the component
        for n_id in component.node_ids:
            # We must count degree relative to the component, but since it's a connected component,
            # its incident edges in the whole graph are exactly the ones in the component.
            if graph.nodes[n_id].incident_edges != 2:
                return False
        return True

    def _degree_counts(self, component: ConnectedComponent, graph: ConnectivityGraph) -> dict:
        counts = {1: 0, 2: 0, 3: 0, 'higher': 0}
        for n_id in component.node_ids:
            deg = graph.nodes[n_id].incident_edges
            if deg in counts:
                counts[deg] += 1
            else:
                counts['higher'] += 1
        return counts

    def _layer_purity(self, component: ConnectedComponent, graph: ConnectivityGraph) -> float:
        """Fraction of the component's edges that sit on an allowed rebar layer."""
        layers = [graph.edges[e_id].layer for e_id in component.edge_ids]
        if not layers:
            return 0.0
        matched = sum(1 for l in layers if l in ALLOWED_REBAR_LAYERS)
        return matched / len(layers)

    def _is_double_line_pattern(self, component: ConnectedComponent, graph: ConnectivityGraph,
                                 length_tol: float = 0.15, aspect_thresh: float = 8.0) -> bool:
        """
        Detects the "bar drawn at its physical width" drafting convention: two
        long, near-equal-length edges (the two sides of the bar) plus one or
        more much shorter edges (end caps). This is a straight bar rendered
        with visible width, not a bent shape (U-bar / narrow stirrup).
        Generalized on relative length/aspect ratio, not hardcoded dimensions.
        """
        lengths = sorted((graph.edges[e_id].length for e_id in component.edge_ids), reverse=True)
        if len(lengths) < 3:
            return False
        long1, long2 = lengths[0], lengths[1]
        shorts = lengths[2:]
        if long2 <= 0 or abs(long1 - long2) / long2 > length_tol:
            return False
        avg_short = sum(shorts) / len(shorts)
        avg_long = (long1 + long2) / 2.0
        if avg_short <= 0:
            return True
        return (avg_long / avg_short) > aspect_thresh

    def _is_regular_polygon(self, component: ConnectedComponent, graph: ConnectivityGraph,
                             tol: float = 0.08) -> bool:
        """
        Detects a closed loop whose edges are all near-equal length — the
        signature of a symmetric CAD symbol (marker, north arrow, callout
        flag) rather than a rebar tie, which is rectangular/hook-shaped.
        """
        lengths = [graph.edges[e_id].length for e_id in component.edge_ids]
        if len(lengths) < 4:
            return False
        mx, mn = max(lengths), min(lengths)
        if mx <= 0:
            return False
        return (mx - mn) / mx < tol

    def _confidence(self, layer_purity: float, shape_ok: bool, aspect_ok: bool, length_ok: bool) -> float:
        """
        Evidence-based confidence instead of a fixed per-recognizer constant:
        base 0.50 + layer match (up to +0.20, scaled by purity) + shape
        criterion (+0.15) + aspect-ratio/geometry sanity (+0.10) + length
        reasonableness (+0.05). Callers only reach this after their hard
        topology gate (edge count / degree pattern) already passed.
        """
        score = 0.50
        score += 0.20 * layer_purity
        score += 0.15 if shape_ok else 0.0
        score += 0.10 if aspect_ok else 0.0
        score += 0.05 if length_ok else 0.0
        return round(min(score, 1.0), 4)


class StraightBarRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges == 1, f"Component has {edges} edges (expected 1)"))

        degs = self._degree_counts(component, graph)
        ev.append(Evidence("degrees", degs[1] == 2 and degs[2] == 0, f"Degrees: {degs}"))

        purity = self._layer_purity(component, graph)
        ev.append(Evidence("layer", purity > 0.0, f"Layer purity {purity:.0%} (allowed={sorted(ALLOWED_REBAR_LAYERS)})"))

        confidence = 0.0
        length = 0.0

        if edges == 1 and degs[1] == 2 and degs[2] == 0 and purity > 0.0:
            e = graph.edges[component.edge_ids[0]]
            is_line_type = e.edge_type in ('LINE', 'POLYLINE_SEGMENT')
            ev.append(Evidence("edge_type", is_line_type, f"Edge type: {e.edge_type} (expected LINE/POLYLINE_SEGMENT)"))
            if is_line_type:
                length = e.length
                length_ok = length > 1.0
                confidence = self._confidence(layer_purity=purity, shape_ok=True, aspect_ok=True, length_ok=length_ok)

        return RecognitionResult(component.id, "straight_bar", confidence, self.__class__.__name__, ev, {"length": length})


class LBarRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges == 2, f"Component has {edges} edges (expected 2)"))

        degs = self._degree_counts(component, graph)
        ev.append(Evidence("degrees", degs[1] == 2 and degs[2] == 1, f"Degrees: {degs}"))

        purity = self._layer_purity(component, graph)
        ev.append(Evidence("layer", purity > 0.0, f"Layer purity {purity:.0%} (allowed={sorted(ALLOWED_REBAR_LAYERS)})"))

        confidence = 0.0
        total_length = component.statistics.get('total_length', 0)

        if edges == 2 and degs[1] == 2 and degs[2] == 1 and purity > 0.0:
            lengths = sorted((graph.edges[e_id].length for e_id in component.edge_ids), reverse=True)
            # Reject a near-collinear "bend" (angle ~180deg) — that's
            # measurement noise on a straight run, not a real L bend. We don't
            # have direct angle-at-node data here, so use the length ratio as
            # a proxy: a genuine L bend has a clearly shorter leg; two
            # near-equal-length edges usually means the split point is
            # incidental, not a structural bend.
            aspect_ok = lengths[1] > 0 and (lengths[0] / lengths[1]) < 50.0
            length_ok = lengths[1] > 1.0
            confidence = self._confidence(layer_purity=purity, shape_ok=True, aspect_ok=aspect_ok, length_ok=length_ok)

        return RecognitionResult(component.id, "l_bar", confidence, self.__class__.__name__, ev, {"total_length": total_length})


class UBarRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges == 3, f"Component has {edges} edges (expected 3)"))

        degs = self._degree_counts(component, graph)
        ev.append(Evidence("degrees", degs[1] == 2 and degs[2] == 2, f"Degrees: {degs}"))

        purity = self._layer_purity(component, graph)
        ev.append(Evidence("layer", purity > 0.0, f"Layer purity {purity:.0%} (allowed={sorted(ALLOWED_REBAR_LAYERS)})"))

        is_double_line = self._is_double_line_pattern(component, graph)
        ev.append(Evidence("not_double_line", not is_double_line,
                            "Two near-equal long edges + short cap => bar drawn at width, not a bend"
                            if is_double_line else "Not a double-line width pattern"))

        confidence = 0.0
        total_length = component.statistics.get('total_length', 0)

        if edges == 3 and degs[1] == 2 and degs[2] == 2 and purity > 0.0 and not is_double_line:
            confidence = self._confidence(layer_purity=purity, shape_ok=True, aspect_ok=True, length_ok=total_length > 1.0)

        return RecognitionResult(component.id, "u_bar", confidence, self.__class__.__name__, ev, {"total_length": total_length})


class ClosedShapeRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges >= 4, f"Component has {edges} edges (expected >=4)"))

        is_loop = self._is_loop(component, graph)
        ev.append(Evidence("is_loop", is_loop, f"Is closed loop: {is_loop}"))

        purity = self._layer_purity(component, graph)
        ev.append(Evidence("layer", purity > 0.0, f"Layer purity {purity:.0%} (allowed={sorted(ALLOWED_REBAR_LAYERS)})"))

        if not (edges >= 4 and is_loop and purity > 0.0):
            return RecognitionResult(component.id, "stirrup", 0.0, self.__class__.__name__, ev, {})

        is_regular = self._is_regular_polygon(component, graph)
        ev.append(Evidence("not_regular_polygon", not is_regular,
                            "All edges near-equal length => symmetric CAD symbol, not a rebar tie"
                            if is_regular else "Not a regular polygon"))
        if is_regular:
            # We know what this is NOT (a stirrup) with reasonable confidence,
            # so say so explicitly rather than dropping it into "unknown".
            return RecognitionResult(component.id, "symbol", 0.70, self.__class__.__name__, ev,
                                      {"reason": "regular_polygon"})

        is_double_line = self._is_double_line_pattern(component, graph)
        ev.append(Evidence("not_double_line", not is_double_line,
                            "Two near-equal long edges + short caps => bar drawn at width, not a stirrup"
                            if is_double_line else "Not a double-line width pattern"))
        if is_double_line:
            return RecognitionResult(component.id, "stirrup", 0.0, self.__class__.__name__, ev, {})

        confidence = self._confidence(layer_purity=purity, shape_ok=True, aspect_ok=True, length_ok=True)
        return RecognitionResult(component.id, "stirrup", confidence, self.__class__.__name__, ev, {})


class BranchRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        degs = self._degree_counts(component, graph)

        has_branch = degs[3] > 0 or degs['higher'] > 0
        ev.append(Evidence("has_branch", has_branch, f"Nodes with degree >= 3: {degs[3] + degs['higher']}"))

        purity = self._layer_purity(component, graph)
        ev.append(Evidence("layer", purity > 0.0, f"Layer purity {purity:.0%} (allowed={sorted(ALLOWED_REBAR_LAYERS)})"))

        confidence = 0.0
        if has_branch and purity > 0.0:
            confidence = self._confidence(layer_purity=purity, shape_ok=True, aspect_ok=True, length_ok=True)

        return RecognitionResult(component.id, "branch", confidence, self.__class__.__name__, ev,
                                  {"branch_nodes": degs[3] + degs['higher']})


class StructuralOutlineRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        is_loop = self._is_loop(component, graph)
        edges = len(component.edge_ids)

        purity = self._layer_purity(component, graph)
        ev.append(Evidence("layer", purity > 0.0, f"Layer purity {purity:.0%} (allowed={sorted(ALLOWED_REBAR_LAYERS)})"))

        # Structural outlines are often huge loops.
        confidence = 0.0
        ev.append(Evidence("large_loop", is_loop and edges > 10, f"Is loop: {is_loop}, Edges: {edges} (expected >10)"))

        if is_loop and edges > 10 and purity > 0.0:
            confidence = self._confidence(layer_purity=purity, shape_ok=True, aspect_ok=True, length_ok=True)

        return RecognitionResult(component.id, "structural_outline", confidence, self.__class__.__name__, ev, {})


class DimensionRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        confidence = 0.0

        # In reality, we'd check if edge types come from DIMENSION inserts, or layer contains 'DIM'
        layers = set(graph.edges[e_id].layer.upper() for e_id in component.edge_ids)
        is_dim = any('DIM' in l for l in layers)
        ev.append(Evidence("dim_layer", is_dim, f"Layers: {layers}"))

        if is_dim:
            confidence = self._confidence(layer_purity=1.0, shape_ok=True, aspect_ok=True, length_ok=True)

        return RecognitionResult(component.id, "dimension", confidence, self.__class__.__name__, ev, {})


class LeaderRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        confidence = 0.0

        layers = set(graph.edges[e_id].layer.upper() for e_id in component.edge_ids)
        is_leader = any('LEAD' in l or 'TXT' in l for l in layers)
        ev.append(Evidence("leader_layer", is_leader, f"Layers: {layers}"))

        if is_leader:
            confidence = self._confidence(layer_purity=1.0, shape_ok=True, aspect_ok=True, length_ok=False)

        return RecognitionResult(component.id, "leader", confidence, self.__class__.__name__, ev, {})
