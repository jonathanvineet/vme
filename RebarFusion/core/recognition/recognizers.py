from core.recognition.models import RecognitionResult, Evidence
from core.recognition.registry import Recognizer
from core.topology.graph import ConnectedComponent, ConnectivityGraph
import math

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

class StraightBarRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        is_straight = False
        
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges == 1, f"Component has {edges} edges (expected 1)"))
        
        degs = self._degree_counts(component, graph)
        ev.append(Evidence("degrees", degs[1] == 2 and degs[2] == 0, f"Degrees: {degs}"))
        
        confidence = 0.0
        length = 0.0
        
        if edges == 1 and degs[1] == 2:
            e = graph.edges[component.edge_ids[0]]
            if e.edge_type in ('LINE', 'POLYLINE_SEGMENT'):
                is_straight = True
                confidence = 0.95
                length = e.length
                
        return RecognitionResult(component.id, "straight_bar", confidence, self.__class__.__name__, ev, {"length": length})

class LBarRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges == 2, f"Component has {edges} edges (expected 2)"))
        
        degs = self._degree_counts(component, graph)
        ev.append(Evidence("degrees", degs[1] == 2 and degs[2] == 1, f"Degrees: {degs}"))
        
        confidence = 0.0
        if edges == 2 and degs[1] == 2 and degs[2] == 1:
            confidence = 0.90
            
        return RecognitionResult(component.id, "l_bar", confidence, self.__class__.__name__, ev, {"total_length": component.statistics.get('total_length', 0)})

class UBarRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges == 3, f"Component has {edges} edges (expected 3)"))
        
        degs = self._degree_counts(component, graph)
        ev.append(Evidence("degrees", degs[1] == 2 and degs[2] == 2, f"Degrees: {degs}"))
        
        confidence = 0.0
        if edges == 3 and degs[1] == 2 and degs[2] == 2:
            confidence = 0.90
            
        return RecognitionResult(component.id, "u_bar", confidence, self.__class__.__name__, ev, {"total_length": component.statistics.get('total_length', 0)})

class StirrupRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        edges = len(component.edge_ids)
        ev.append(Evidence("edge_count", edges >= 4, f"Component has {edges} edges (expected >=4)"))
        
        is_loop = self._is_loop(component, graph)
        ev.append(Evidence("is_loop", is_loop, f"Is closed loop: {is_loop}"))
        
        confidence = 0.0
        if edges >= 4 and is_loop:
            # We don't want to confuse a structural outline with a stirrup.
            # Stirrups usually have a small bounding box. We can check bbox size as a heuristic, but for now just loop check.
            confidence = 0.85
            
        return RecognitionResult(component.id, "stirrup", confidence, self.__class__.__name__, ev, {})

class BranchRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        degs = self._degree_counts(component, graph)
        
        has_branch = degs[3] > 0 or degs['higher'] > 0
        ev.append(Evidence("has_branch", has_branch, f"Nodes with degree >= 3: {degs[3] + degs['higher']}"))
        
        confidence = 0.0
        if has_branch:
            confidence = 0.95
            
        return RecognitionResult(component.id, "branch", confidence, self.__class__.__name__, ev, {"branch_nodes": degs[3] + degs['higher']})

class StructuralOutlineRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        is_loop = self._is_loop(component, graph)
        edges = len(component.edge_ids)
        
        # Structural outlines are often huge loops. 
        # If it's a loop with many edges, or a huge bounding box...
        confidence = 0.0
        ev.append(Evidence("large_loop", is_loop and edges > 10, f"Is loop: {is_loop}, Edges: {edges} (expected >10)"))
        
        if is_loop and edges > 10:
            confidence = 0.86 # slightly higher than stirrup for large loops
            
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
            confidence = 0.90
            
        return RecognitionResult(component.id, "dimension", confidence, self.__class__.__name__, ev, {})

class LeaderRecognizer(BaseShapeRecognizer):
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        ev = []
        confidence = 0.0
        
        layers = set(graph.edges[e_id].layer.upper() for e_id in component.edge_ids)
        is_leader = any('LEAD' in l or 'TXT' in l for l in layers)
        
        if is_leader:
            confidence = 0.80
            
        return RecognitionResult(component.id, "leader", confidence, self.__class__.__name__, ev, {})
