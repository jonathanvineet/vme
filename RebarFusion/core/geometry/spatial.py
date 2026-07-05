import time
import math
from scipy.spatial import cKDTree
from typing import List, Dict, Optional, Tuple
from core.context import AnalysisContext
from core.pipeline import PipelineStage
from core.geometry.entities import Point, LineEntity, ArcEntity, PolylineEntity, TextEntity
from core.geometry.repository import GeometryRepository
import uuid

class SpatialIndex:
    """
    A service that provides fast spatial queries on the geometry repository.
    """
    def __init__(self, repo: GeometryRepository):
        self.repo = repo
        self._build_kdtree()

    def _arc_endpoints(self, arc: ArcEntity) -> Tuple[Point, Point]:
        rad_start = math.radians(arc.start_angle)
        rad_end = math.radians(arc.end_angle)
        p1 = Point(
            arc.center.x + arc.radius * math.cos(rad_start),
            arc.center.y + arc.radius * math.sin(rad_start),
            arc.center.z
        )
        p2 = Point(
            arc.center.x + arc.radius * math.cos(rad_end),
            arc.center.y + arc.radius * math.sin(rad_end),
            arc.center.z
        )
        return p1, p2

    def _build_kdtree(self):
        self.points = []
        self.point_refs = [] # (entity_uuid, point_type/index)
        
        # We index all critical points of geometries for nearest neighbor searches
        for e in self.repo.lines.values():
            self.points.append(e.start.as_tuple())
            self.point_refs.append((e.id, 'start'))
            self.points.append(e.end.as_tuple())
            self.point_refs.append((e.id, 'end'))
            
        for e in self.repo.arcs.values():
            p1, p2 = self._arc_endpoints(e)
            self.points.append(p1.as_tuple())
            self.point_refs.append((e.id, 'start'))
            self.points.append(p2.as_tuple())
            self.point_refs.append((e.id, 'end'))
            
        for e in self.repo.polylines.values():
            for i, v in enumerate(e.vertices):
                self.points.append(v.as_tuple())
                self.point_refs.append((e.id, f'vertex_{i}'))
                
        for e in self.repo.texts.values():
            self.points.append(e.insert.as_tuple())
            self.point_refs.append((e.id, 'insert'))
            
        if self.points:
            self.kdtree = cKDTree(self.points)
        else:
            self.kdtree = None

    def query_radius(self, pt: Point, r: float) -> List[Tuple[uuid.UUID, str]]:
        if not self.kdtree:
            return []
        indices = self.kdtree.query_ball_point(pt.as_tuple(), r=r)
        return [self.point_refs[i] for i in indices]
        
    def nearest_point(self, pt: Point) -> Optional[Tuple[uuid.UUID, str, float]]:
        if not self.kdtree:
            return None
        dist, idx = self.kdtree.query(pt.as_tuple(), k=1)
        if isinstance(dist, list) or isinstance(dist, tuple):
            dist = dist[0]
            idx = idx[0]
        return self.point_refs[idx][0], self.point_refs[idx][1], dist


class SpatialIndexStage(PipelineStage):
    @property
    def name(self) -> str:
        return "spatial_index"
        
    def execute(self, context: AnalysisContext) -> AnalysisContext:
        start_time = time.time()
        
        spatial_index = SpatialIndex(context.repository)
        
        duration = time.time() - start_time
        
        new_context = context.evolve(spatial_index=spatial_index)
        # emit event with number of indexed points
        indexed_points = len(spatial_index.points) if hasattr(spatial_index, 'points') else 0
        self._emit_event(new_context, indexed_points, duration)
        
        return new_context
