from __future__ import annotations

import math
import bisect
from collections import defaultdict
from typing import List, Tuple, Dict, Any, Optional
from uuid import UUID

import scipy.spatial
import numpy as np

from core.geometry.canonical import CanonicalRepository, CanonicalEntity

class PointIndex:
    def __init__(self, entities: List[CanonicalEntity]):
        self.points = []
        self.uuids = []
        
        for e in entities:
            # We index a centroid or important points for each entity
            if hasattr(e, 'start') and hasattr(e, 'end'):
                mid_x = (e.start[0] + e.end[0]) / 2.0
                mid_y = (e.start[1] + e.end[1]) / 2.0
                self.points.append([mid_x, mid_y])
                self.uuids.append(e.id)
            elif hasattr(e, 'center'):
                self.points.append([e.center[0], e.center[1]])
                self.uuids.append(e.id)
            elif hasattr(e, 'vertices') and e.vertices:
                # polyline centroid approx
                xs = [v[0] for v in e.vertices]
                ys = [v[1] for v in e.vertices]
                self.points.append([sum(xs)/len(xs), sum(ys)/len(ys)])
                self.uuids.append(e.id)
            elif hasattr(e, 'insertion_point'):
                self.points.append([e.insertion_point[0], e.insertion_point[1]])
                self.uuids.append(e.id)
            elif hasattr(e, 'defpoint'):
                self.points.append([e.defpoint[0], e.defpoint[1]])
                self.uuids.append(e.id)
            elif hasattr(e, 'bounding_box') and e.bounding_box != (0.0, 0.0, 0.0, 0.0):
                # Fallback to bbox center
                bb = e.bounding_box
                self.points.append([(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0])
                self.uuids.append(e.id)
                
        if self.points:
            self.kdtree = scipy.spatial.KDTree(np.array(self.points))
        else:
            self.kdtree = None

    def nearest_point(self, point: Tuple[float, float], k: int = 1, max_dist: float = float('inf')) -> List[Tuple[UUID, float]]:
        if not self.kdtree:
            return []
        
        dist, idx = self.kdtree.query(np.array([point[0], point[1]]), k=k, distance_upper_bound=max_dist)
        
        results = []
        if k == 1:
            if idx != self.kdtree.n:
                results.append((self.uuids[idx], dist))
        else:
            for d, i in zip(dist, idx):
                if i != self.kdtree.n:
                    results.append((self.uuids[i], d))
                    
        return results
        
    def within_radius(self, point: Tuple[float, float], radius: float) -> List[Tuple[UUID, float]]:
        if not self.kdtree:
            return []
            
        indices = self.kdtree.query_ball_point(np.array([point[0], point[1]]), r=radius)
        
        results = []
        # Calculate distances for results
        pt = np.array([point[0], point[1]])
        for idx in indices:
            d = np.linalg.norm(self.kdtree.data[idx] - pt)
            results.append((self.uuids[idx], float(d)))
            
        # Sort by distance
        results.sort(key=lambda x: x[1])
        return results

class BBoxIndex:
    def __init__(self, entities: List[CanonicalEntity]):
        # Simple sorted array by X-min for sweeping
        self.bboxes = []
        for e in entities:
            bb = e.bounding_box
            if bb != (0.0, 0.0, 0.0, 0.0):
                self.bboxes.append((bb[0], bb[1], bb[2], bb[3], e.id))
                
        self.bboxes.sort(key=lambda x: x[0])  # Sort by x_min
        
        # We can extract just x_mins for bisect
        self.x_mins = [b[0] for b in self.bboxes]
        
    def intersect_bbox(self, bbox: Tuple[float, float, float, float]) -> List[UUID]:
        min_x, min_y, max_x, max_y = bbox
        
        # Find first entity whose max_x >= our min_x? Wait, we are sorted by min_x.
        # So we can find all entities whose min_x <= our max_x.
        # But we must iterate from beginning to finding index of (min_x <= max_x).
        # Actually, if we sort by min_x, we can bisect to find the right edge of possibilities:
        right_idx = bisect.bisect_right(self.x_mins, max_x)
        
        results = []
        # We still have to check all from 0 to right_idx because a very wide entity might start early.
        for i in range(right_idx):
            b = self.bboxes[i]
            # b = (ex_min, ey_min, ex_max, ey_max, uuid)
            # check intersection
            if not (b[2] < min_x or b[0] > max_x or b[3] < min_y or b[1] > max_y):
                results.append(b[4])
                
        return results

    def entities_within_bbox(self, bbox: Tuple[float, float, float, float]) -> List[UUID]:
        min_x, min_y, max_x, max_y = bbox
        
        right_idx = bisect.bisect_right(self.x_mins, max_x)
        
        results = []
        for i in range(right_idx):
            b = self.bboxes[i]
            # Check if strictly within
            if b[0] >= min_x and b[2] <= max_x and b[1] >= min_y and b[3] <= max_y:
                results.append(b[4])
                
        return results

class OrientationIndex:
    def __init__(self, entities: List[CanonicalEntity]):
        self.buckets = defaultdict(list)
        
        for e in entities:
            angle = None
            if hasattr(e, 'direction') and e.direction != (0.0, 0.0, 0.0):
                dx, dy = e.direction[0], e.direction[1]
                angle = math.degrees(math.atan2(dy, dx))
            elif hasattr(e, 'start_angle') and hasattr(e, 'end_angle'):
                angle = e.start_angle # or maybe mid angle
                
            if angle is not None:
                # normalize to [0, 180) for lines (undirected)
                # arcs are directed, but for simplicity we bucket [0, 360) in integers
                angle = angle % 180.0
                if angle < 0:
                    angle += 180.0
                    
                bucket = int(round(angle)) % 180
                self.buckets[bucket].append(e.id)
                
    def query_orientation(self, angle_deg: float, tolerance_deg: float = 2.0) -> List[UUID]:
        angle_deg = (angle_deg % 180.0 + 180.0) % 180.0
        
        results = []
        
        # Check buckets within tolerance
        min_bucket = int(math.floor(angle_deg - tolerance_deg))
        max_bucket = int(math.ceil(angle_deg + tolerance_deg))
        
        for b in range(min_bucket, max_bucket + 1):
            normalized_b = b % 180
            # Verify exact angle distance for items in bucket
            # We don't have exact angle stored here, so we return all in bucket 
            # and let the caller filter, or we just return them all.
            # Returning all in matching buckets is fast.
            results.extend(self.buckets[normalized_b])
            
        return list(set(results))

class SemanticIndex:
    def __init__(self, entities: List[CanonicalEntity]):
        self.by_layer = defaultdict(list)
        self.by_type = defaultdict(list)
        self.by_hash = defaultdict(list)
        
        for e in entities:
            self.by_layer[e.layer].append(e.id)
            self.by_type[e.dxf_type].append(e.id)
            self.by_hash[e.geometry_hash].append(e.id)
            
class LengthIndex:
    def __init__(self, entities: List[CanonicalEntity]):
        self.lengths = []
        
        for e in entities:
            if hasattr(e, 'length'):
                self.lengths.append((e.length, e.id))
            elif hasattr(e, 'radius'):
                self.lengths.append((e.radius, e.id)) # useful for circles/arcs
                
        self.lengths.sort(key=lambda x: x[0])
        self.length_vals = [x[0] for x in self.lengths]
        
    def similar_length(self, target: float, tolerance_pct: float = 0.05) -> List[UUID]:
        min_len = target * (1.0 - tolerance_pct)
        max_len = target * (1.0 + tolerance_pct)
        
        left = bisect.bisect_left(self.length_vals, min_len)
        right = bisect.bisect_right(self.length_vals, max_len)
        
        return [self.lengths[i][1] for i in range(left, right)]
