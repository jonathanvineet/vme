from typing import Dict, List, Tuple, Optional
from uuid import UUID
import uuid

from core.topology.graph import ConnectivityGraph, ConnectedComponent
from core.recognition.registry import RecognitionCache
from core.spatial.engine import SpatialQueryEngine
from core.recognition.annotations import Annotation, AnnotationToken
from core.engineering.models import (
    AssociationCandidate, Evidence, EngineeringConstraint, 
    DiameterConstraint, SpacingConstraint, MarkConstraint, LengthConstraint, CountConstraint
)

class AnnotationGroup:
    def __init__(self, annotations: List[Annotation], tokens: List[AnnotationToken], centroid: Tuple[float, float, float], leader_endpoint: Optional[Tuple[float, float, float]] = None):
        self.uuid = uuid.uuid4()
        self.annotations = annotations
        self.tokens = tokens
        self.centroid = centroid
        self.leader_endpoint = leader_endpoint

class EngineeringAssociationEngine:
    def __init__(self, graph: ConnectivityGraph, comp_repo, spatial_engine: SpatialQueryEngine, cache: RecognitionCache):
        self.graph = graph
        self.comp_repo = comp_repo
        self.spatial = spatial_engine
        self.cache = cache

    def cluster_annotations(self, annotations: List[Annotation], parser, leaders: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]) -> List[AnnotationGroup]:
        """
        Group annotations based on spatial proximity (within 300mm) and leader association.
        """
        groups: List[AnnotationGroup] = []
        visited = set()

        # Build groups based on leader attachment first
        for leader in leaders:
            p1, p2 = leader
            attached_anns = []
            
            # Check proximity of either endpoint to determine if it is near the annotation
            for ann in annotations:
                if ann.uuid in visited:
                    continue
                d1 = ((ann.insertion[0] - p1[0])**2 + (ann.insertion[1] - p1[1])**2)**0.5
                d2 = ((ann.insertion[0] - p2[0])**2 + (ann.insertion[1] - p2[1])**2)**0.5
                if min(d1, d2) < 800.0:  # Allow 800mm tolerance for leader landing near text
                    attached_anns.append(ann)
            
            if attached_anns:
                # Mark as visited
                for ann in attached_anns:
                    visited.add(ann.uuid)
                    
                tokens = []
                for a in attached_anns:
                    tokens.extend(parser.parse(a))
                xs = [a.insertion[0] for a in attached_anns]
                ys = [a.insertion[1] for a in attached_anns]
                centroid = (sum(xs)/len(xs), sum(ys)/len(ys), 0.0)
                
                # Determine which leader point is further from text centroid (the rebar pointer end)
                dc1 = ((centroid[0] - p1[0])**2 + (centroid[1] - p1[1])**2)**0.5
                dc2 = ((centroid[0] - p2[0])**2 + (centroid[1] - p2[1])**2)**0.5
                pointer_end = p2 if dc1 < dc2 else p1
                
                groups.append(AnnotationGroup(attached_anns, tokens, centroid, pointer_end))

        # Cluster remaining unassociated annotations by proximity
        for i, ann in enumerate(annotations):
            if ann.uuid in visited:
                continue
            
            cluster = [ann]
            visited.add(ann.uuid)
            
            # Find close unvisited text entities
            for other in annotations[i+1:]:
                if other.uuid in visited:
                    continue
                dist = ((ann.insertion[0] - other.insertion[0])**2 + (ann.insertion[1] - other.insertion[1])**2)**0.5
                if dist < 400.0:  # 400mm clustering radius
                    cluster.append(other)
                    visited.add(other.uuid)
            
            tokens = []
            for a in cluster:
                tokens.extend(parser.parse(a))
            xs = [a.insertion[0] for a in cluster]
            ys = [a.insertion[1] for a in cluster]
            centroid = (sum(xs)/len(xs), sum(ys)/len(ys), 0.0)
            groups.append(AnnotationGroup(cluster, tokens, centroid))

        return groups

    def find_group_candidates(self, group: AnnotationGroup, k: int = 5) -> List[AssociationCandidate]:
        """
        Finds the top-K component candidates for an annotation group.
        Uses leader tip if available, falling back to KDTree centroid query.
        """
        # If leader tip is present, search directly from the pointer end
        if group.leader_endpoint:
            x, y, _ = group.leader_endpoint
            radius = 1200.0  # Wider to catch close rebar; leader is still precise
        else:
            x, y, _ = group.centroid
            radius = 6000.0  # Wide radius: annotations may be in legend/table away from bars

        results = self.spatial.within_radius((x, y), radius)
        nearby_geom_ids = {r.entity.id for r in results}

        candidates_map: Dict[UUID, AssociationCandidate] = {}

        for comp in self.comp_repo.components.values():
            recog_result = self.cache.get(comp.id)
            if not recog_result or recog_result.label in ['unknown', 'dimension', 'structural_outline']:
                continue
            # Only associate with rebar-layer components
            if comp.edge_ids:
                first_edge = self.graph.edges.get(comp.edge_ids[0])
                if first_edge and 'RBAR' not in first_edge.layer.upper():
                    continue

            comp_geom_ids = set()
            for edge_id in comp.edge_ids:
                edge = self.graph.edges.get(edge_id)
                if edge:
                    comp_geom_ids.add(edge.geometry_uuid)

            intersection = comp_geom_ids.intersection(nearby_geom_ids)
            if not intersection:
                continue

            # Check if this group contains a dimension with endpoints
            dimension_anns = [a for a in group.annotations if a.annotation_type == 'DIMENSION' and a.p1 and a.p2]
            
            # Calculate nearest distance to the search point or segment
            min_dist = float('inf')
            for node_id in comp.node_ids:
                node = self.graph.nodes.get(node_id)
                if node:
                    nx, ny, _ = node.position
                    if dimension_anns:
                        # Find minimum distance to any dimension line segment
                        for dim in dimension_anns:
                            # Projection helper
                            dx = dim.p2[0] - dim.p1[0]
                            dy = dim.p2[1] - dim.p1[1]
                            if dx == 0 and dy == 0:
                                dist = ((nx - dim.p1[0])**2 + (ny - dim.p1[1])**2)**0.5
                            else:
                                t = ((nx - dim.p1[0]) * dx + (ny - dim.p1[1]) * dy) / (dx*dx + dy*dy)
                                t = max(0.0, min(1.0, t))
                                proj_x = dim.p1[0] + t * dx
                                proj_y = dim.p1[1] + t * dy
                                dist = ((nx - proj_x)**2 + (ny - proj_y)**2)**0.5
                            if dist < min_dist:
                                min_dist = dist
                    else:
                        # Centroid distance
                        dist = ((nx - x)**2 + (ny - y)**2)**0.5
                        if dist < min_dist:
                            min_dist = dist

            evidence = []
            
            # Leader Evidence (near 1.0 confidence)
            if group.leader_endpoint and min_dist < 1000.0:
                score = 0.95
                evidence.append(Evidence("leader_ptr", 0.95, f"Leader points within {min_dist:.1f}mm of component", comp.id))
            else:
                # Proximity evidence
                proximity_score = max(0.0, 1.0 - (min_dist / radius))
                score = proximity_score * 0.8
                evidence.append(Evidence("distance", score, f"Distance from group centroid: {min_dist:.1f}mm (radius {radius:.0f}mm)", comp.id))

            # Combine all tokens from the group for the candidate
            for token in group.tokens:
                cand = AssociationCandidate(
                    component_uuid=comp.id,
                    token=token,
                    score=score,
                    evidence=evidence
                )
                
                # Deduplicate or group by component per token type
                key = (comp.id, token.token_type)
                if key not in candidates_map or candidates_map[key].score < score:
                    candidates_map[key] = cand

        sorted_cands = sorted(candidates_map.values(), key=lambda c: c.score, reverse=True)
        return sorted_cands[:k]

    def build_constraints(self, candidates: List[AssociationCandidate]) -> List[EngineeringConstraint]:
        constraints = []
        for cand in candidates:
            if cand.score >= 0.5:
                ttype = cand.token.token_type
                if ttype == 'TOKEN_DIAMETER':
                    constraints.append(DiameterConstraint(cand.token, cand.component_uuid, cand.score))
                elif ttype == 'TOKEN_SPACING':
                    constraints.append(SpacingConstraint(cand.token, cand.component_uuid, cand.score))
                elif ttype == 'TOKEN_MARK':
                    constraints.append(MarkConstraint(cand.token, cand.component_uuid, cand.score))
                elif ttype == 'TOKEN_LENGTH':
                    constraints.append(LengthConstraint(cand.token, cand.component_uuid, cand.score))
                elif ttype == 'TOKEN_COUNT':
                    constraints.append(CountConstraint(cand.token, cand.component_uuid, cand.score))
        return constraints
