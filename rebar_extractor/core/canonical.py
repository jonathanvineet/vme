import time
import math
from typing import Dict, List, Tuple
from core.context import AnalysisContext
from core.pipeline import PipelineStage
from core.geometry import Point
import uuid
from dataclasses import dataclass, field

@dataclass
class CanonicalNode:
    id: int
    point: Point
    # The geometries and specific points that share this exact coordinate
    # List of (geometry_uuid, point_type)
    references: List[Tuple[uuid.UUID, str]] = field(default_factory=list)
    degree: int = 0

class CanonicalNodesStage(PipelineStage):
    @property
    def name(self) -> str:
        return "canonical_nodes"
        
    def execute(self, context: AnalysisContext) -> AnalysisContext:
        start_time = time.time()
        
        # We can extract all points from the spatial index since it already collected them!
        spatial = context.spatial_index
        if not spatial:
            raise ValueError("SpatialIndex is required before CanonicalNodesStage")
            
        nodes_map: Dict[Tuple[float, float, float], CanonicalNode] = {}
        next_id = 1
        
        for idx, pt_tuple in enumerate(spatial.points):
            ref = spatial.point_refs[idx]
            
            if pt_tuple not in nodes_map:
                nodes_map[pt_tuple] = CanonicalNode(
                    id=next_id,
                    point=Point(pt_tuple[0], pt_tuple[1], pt_tuple[2])
                )
                next_id += 1
                
            nodes_map[pt_tuple].references.append(ref)
            
        canonical_nodes_list = list(nodes_map.values())
        
        duration = time.time() - start_time
        
        new_context = context.evolve(canonical_nodes=canonical_nodes_list)
        self._emit_event(new_context, len(canonical_nodes_list), duration)
        
        return new_context
