from typing import List, Tuple, Optional, Dict
from uuid import UUID

from core.geometry.canonical import CanonicalRepository, CanonicalEntity, CanonicalText, CanonicalDimension
from core.spatial.result import QueryResult
from core.spatial.indexes import PointIndex, BBoxIndex, OrientationIndex, SemanticIndex, LengthIndex
import math

class SpatialQueryEngine:
    def __init__(self, repo: CanonicalRepository):
        self._repo = repo
        self._entities: Dict[UUID, CanonicalEntity] = {e.id: e for e in repo.all_entities()}
        
        # Build indexes
        entities_list = list(self._entities.values())
        self._point_index = PointIndex(entities_list)
        self._bbox_index = BBoxIndex(entities_list)
        self._orientation_index = OrientationIndex(entities_list)
        self._semantic_index = SemanticIndex(entities_list)
        self._length_index = LengthIndex(entities_list)

    @classmethod
    def build(cls, repo: CanonicalRepository) -> 'SpatialQueryEngine':
        return cls(repo)
        
    def _resolve(self, uuids: List[UUID]) -> List[CanonicalEntity]:
        return [self._entities[u] for u in uuids if u in self._entities]

    def _resolve_with_dist(self, results: List[Tuple[UUID, float]], index_used: str) -> List[QueryResult]:
        final = []
        for u, d in results:
            if u in self._entities:
                final.append(QueryResult(entity=self._entities[u], distance=d, index_used=index_used))
        return final

    # Point queries (KDTree)
    def nearest_point(self, point: Tuple[float, float], k: int = 1, max_dist: float = float('inf')) -> List[QueryResult]:
        res = self._point_index.nearest_point(point, k, max_dist)
        return self._resolve_with_dist(res, "point_kdtree")

    def within_radius(self, point: Tuple[float, float], radius: float) -> List[QueryResult]:
        res = self._point_index.within_radius(point, radius)
        return self._resolve_with_dist(res, "point_kdtree")

    # Bounding box queries (sorted interval list)
    def intersect_bbox(self, bbox: Tuple[float, float, float, float]) -> List[QueryResult]:
        res = self._bbox_index.intersect_bbox(bbox)
        ents = self._resolve(res)
        return [QueryResult(entity=e, distance=0.0, index_used="bbox_sweep") for e in ents]

    def entities_within_bbox(self, bbox: Tuple[float, float, float, float]) -> List[QueryResult]:
        res = self._bbox_index.entities_within_bbox(bbox)
        ents = self._resolve(res)
        return [QueryResult(entity=e, distance=0.0, index_used="bbox_sweep") for e in ents]

    # Semantic attribute queries (dict lookups — O(1))
    def query_layer(self, layer_name: str) -> List[CanonicalEntity]:
        return self._resolve(self._semantic_index.by_layer.get(layer_name, []))

    def query_type(self, dxf_type: str) -> List[CanonicalEntity]:
        return self._resolve(self._semantic_index.by_type.get(dxf_type, []))

    def fingerprint_lookup(self, geometry_hash: str) -> List[CanonicalEntity]:
        return self._resolve(self._semantic_index.by_hash.get(geometry_hash, []))

    # Derived geometric queries (index lookups — O(log n))
    def query_orientation(self, angle_deg: float, tolerance_deg: float = 2.0) -> List[CanonicalEntity]:
        uuids = self._orientation_index.query_orientation(angle_deg, tolerance_deg)
        return self._resolve(uuids)

    def parallel(self, entity: CanonicalEntity, tolerance_deg: float = 2.0) -> List[CanonicalEntity]:
        if not hasattr(entity, 'direction'):
            return []
        
        dx, dy = entity.direction[0], entity.direction[1]
        if dx == 0 and dy == 0:
            return []
            
        angle = math.degrees(math.atan2(dy, dx))
        results = self.query_orientation(angle, tolerance_deg)
        # Exclude self
        return [e for e in results if e.id != entity.id]

    def similar_length(self, entity: CanonicalEntity, tolerance_pct: float = 0.05) -> List[CanonicalEntity]:
        val = None
        if hasattr(entity, 'length'):
            val = entity.length
        elif hasattr(entity, 'radius'):
            val = entity.radius
            
        if val is None:
            return []
            
        uuids = self._length_index.similar_length(val, tolerance_pct)
        results = self._resolve(uuids)
        return [e for e in results if e.id != entity.id]

    # Spatial relationship queries
    def nearest_entity(self, entity: CanonicalEntity, k: int = 1, max_dist: float = float('inf')) -> List[QueryResult]:
        pt = None
        if hasattr(entity, 'bounding_box') and entity.bounding_box != (0.0, 0.0, 0.0, 0.0):
            bb = entity.bounding_box
            pt = ((bb[0]+bb[2])/2.0, (bb[1]+bb[3])/2.0)
        
        if pt is None:
            return []
            
        # Add 1 to k to account for finding itself
        results = self.nearest_point(pt, k=k+1, max_dist=max_dist)
        return [r for r in results if r.entity.id != entity.id][:k]

    def text_near(self, entity: CanonicalEntity, max_dist: float) -> List[CanonicalText]:
        pt = None
        if hasattr(entity, 'bounding_box') and entity.bounding_box != (0.0, 0.0, 0.0, 0.0):
            bb = entity.bounding_box
            pt = ((bb[0]+bb[2])/2.0, (bb[1]+bb[3])/2.0)
            
        if pt is None:
            return []
            
        nearby = self.within_radius(pt, max_dist)
        return [r.entity for r in nearby if r.entity.dxf_type in ("TEXT", "MTEXT") and r.entity.id != entity.id]

    def dimension_near(self, entity: CanonicalEntity, max_dist: float) -> List[CanonicalDimension]:
        pt = None
        if hasattr(entity, 'bounding_box') and entity.bounding_box != (0.0, 0.0, 0.0, 0.0):
            bb = entity.bounding_box
            pt = ((bb[0]+bb[2])/2.0, (bb[1]+bb[3])/2.0)
            
        if pt is None:
            return []
            
        nearby = self.within_radius(pt, max_dist)
        return [r.entity for r in nearby if r.entity.dxf_type == "DIMENSION" and r.entity.id != entity.id]
