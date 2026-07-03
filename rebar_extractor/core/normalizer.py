from core.geometry import (
    Point, GeometryEntity, LineEntity, ArcEntity, 
    PolylineEntity, BlockReference, TextEntity, DimensionEntity
)
from typing import List
import math

class Normalizer:
    def __init__(self):
        pass
        
    def _rotate_point(self, pt: Point, angle_deg: float) -> Point:
        if angle_deg == 0.0:
            return Point(pt.x, pt.y, pt.z)
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return Point(
            pt.x * cos_a - pt.y * sin_a,
            pt.x * sin_a + pt.y * cos_a,
            pt.z
        )

    def _transform_point(self, pt: Point, insert: Point, rotation: float, sx: float, sy: float) -> Point:
        scaled = Point(pt.x * sx, pt.y * sy, pt.z)
        rotated = self._rotate_point(scaled, rotation)
        return Point(rotated.x + insert.x, rotated.y + insert.y, rotated.z + insert.z)

    def normalize(self, entities: List[GeometryEntity]) -> List[GeometryEntity]:
        flat_entities = []
        for e in entities:
            if isinstance(e, BlockReference):
                flat_entities.extend(self._explode_block(e, Point(0,0,0), 0.0, 1.0, 1.0))
            else:
                flat_entities.append(e)
                
        # Deduplication
        deduped = self._deduplicate(flat_entities)
        return deduped
        
    def _explode_block(self, block: BlockReference, parent_insert: Point, parent_rot: float, parent_sx: float, parent_sy: float) -> List[GeometryEntity]:
        result = []
        abs_sx = parent_sx * block.scale_x
        abs_sy = parent_sy * block.scale_y
        abs_rot = parent_rot + block.rotation
        abs_insert = self._transform_point(block.insert, parent_insert, parent_rot, parent_sx, parent_sy)

        for sub_e in block.entities:
            if isinstance(sub_e, BlockReference):
                result.extend(self._explode_block(sub_e, abs_insert, abs_rot, abs_sx, abs_sy))
            elif isinstance(sub_e, LineEntity):
                result.append(LineEntity(
                    layer=sub_e.layer, color=sub_e.color,
                    start=self._transform_point(sub_e.start, abs_insert, abs_rot, abs_sx, abs_sy),
                    end=self._transform_point(sub_e.end, abs_insert, abs_rot, abs_sx, abs_sy)
                ))
            elif isinstance(sub_e, ArcEntity):
                result.append(ArcEntity(
                    layer=sub_e.layer, color=sub_e.color,
                    center=self._transform_point(sub_e.center, abs_insert, abs_rot, abs_sx, abs_sy),
                    radius=sub_e.radius * abs_sx,
                    start_angle=sub_e.start_angle + abs_rot,
                    end_angle=sub_e.end_angle + abs_rot
                ))
            elif isinstance(sub_e, PolylineEntity):
                new_vertices = [self._transform_point(v, abs_insert, abs_rot, abs_sx, abs_sy) for v in sub_e.vertices]
                result.append(PolylineEntity(
                    layer=sub_e.layer, color=sub_e.color,
                    vertices=new_vertices,
                    is_closed=sub_e.is_closed
                ))
            elif isinstance(sub_e, TextEntity):
                result.append(TextEntity(
                    layer=sub_e.layer, color=sub_e.color,
                    insert=self._transform_point(sub_e.insert, abs_insert, abs_rot, abs_sx, abs_sy),
                    text=sub_e.text,
                    height=sub_e.height * abs_sy
                ))
            elif isinstance(sub_e, DimensionEntity):
                result.append(DimensionEntity(
                    layer=sub_e.layer, color=sub_e.color,
                    defpoint=self._transform_point(sub_e.defpoint, abs_insert, abs_rot, abs_sx, abs_sy),
                    text_midpoint=self._transform_point(sub_e.text_midpoint, abs_insert, abs_rot, abs_sx, abs_sy),
                    measurement=sub_e.measurement * abs_sx,
                    text=sub_e.text
                ))
                
        return result
        
    def _deduplicate(self, entities: List[GeometryEntity]) -> List[GeometryEntity]:
        seen = set()
        deduped = []
        for e in entities:
            def r(val): return round(val, 2)
            def r_pt(pt): return (r(pt.x), r(pt.y), r(pt.z))
            
            if isinstance(e, LineEntity):
                pts = tuple(sorted([r_pt(e.start), r_pt(e.end)]))
                h = ("LINE", pts)
            elif isinstance(e, ArcEntity):
                h = ("ARC", r_pt(e.center), r(e.radius), r(e.start_angle), r(e.end_angle))
            elif isinstance(e, PolylineEntity):
                pts = tuple([r_pt(v) for v in e.vertices])
                h = ("POLYLINE", pts, e.is_closed)
            elif isinstance(e, TextEntity):
                h = ("TEXT", r_pt(e.insert), e.text)
            elif isinstance(e, DimensionEntity):
                h = ("DIMENSION", r_pt(e.defpoint), r_pt(e.text_midpoint), e.text)
            else:
                h = id(e)
                
            if h not in seen:
                seen.add(h)
                deduped.append(e)
                
        return deduped
