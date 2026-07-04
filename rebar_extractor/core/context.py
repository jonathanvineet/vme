from dataclasses import dataclass, field
from typing import Dict, Any, List
from core.repository import GeometryRepository

@dataclass
class PhaseCompletedEvent:
    phase: str
    entities: int
    duration: float
    warnings: List[str]

@dataclass(frozen=True)
class AnalysisContext:
    filepath: str
    repository: GeometryRepository = field(default_factory=GeometryRepository)
    spatial_index: Any = None
    topology: Any = None
    canonical_nodes: Any = None
    annotation_graph: Any = None
    
    # We use lists and dicts here; though frozen, the references are stable. 
    # To be strictly immutable, we could return new contexts, but modifying these 
    # collections is an acceptable pythonic compromise for metrics/events.
    metrics: Dict[str, Any] = field(default_factory=dict)
    events: List[PhaseCompletedEvent] = field(default_factory=list)
    
    def evolve(self, **kwargs) -> 'AnalysisContext':
        """Create a new context with updated fields (Immutable State pattern)"""
        current = {
            "filepath": self.filepath,
            "repository": self.repository,
            "spatial_index": self.spatial_index,
            "topology": self.topology,
            "canonical_nodes": self.canonical_nodes,
            "annotation_graph": self.annotation_graph,
            "metrics": self.metrics.copy(),
            "events": list(self.events)
        }
        current.update(kwargs)
        return AnalysisContext(**current)
