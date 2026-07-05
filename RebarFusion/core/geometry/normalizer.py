import uuid
import math
from typing import List
from core.geometry.entities import (
    Point, GeometryEntity, LineEntity, ArcEntity, 
    PolylineEntity, BlockReference, TextEntity, DimensionEntity
)
from core.geometry.repository import GeometryRepository

class Normalizer:
    def __init__(self, repo: GeometryRepository):
        self.repo = repo
        
    def _round_float(self, val: float, decimals: int = 5) -> float:
        return round(val, decimals)
        
    def _round_point(self, pt: Point) -> Point:
        return Point(
            self._round_float(pt.x),
            self._round_float(pt.y),
            self._round_float(pt.z)
        )

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
        transformed = Point(rotated.x + insert.x, rotated.y + insert.y, rotated.z + insert.z)
        return self._round_point(transformed)

    def normalize(self, entities: List[GeometryEntity]):
        for e in entities:
            if isinstance(e, BlockReference):
                # Add block itself to repo
                self.repo.add(e)
                # Explode children and add their UUIDs to this block
                sub_entities = e.metadata.get("_parsed_entities", [])
                children = self._explode_block(sub_entities, e, Point(0,0,0), 0.0, 1.0, 1.0)
                e.children = [c.id for c in children]
            else:
                self._normalize_primitive(e)
                self.repo.add(e)
                
    def _normalize_primitive(self, e: GeometryEntity):
        if isinstance(e, LineEntity):
            e.start = self._round_point(e.start)
            e.end = self._round_point(e.end)
        elif isinstance(e, ArcEntity):
            e.center = self._round_point(e.center)
            e.radius = self._round_float(e.radius)
            e.start_angle = self._round_float(e.start_angle)
            e.end_angle = self._round_float(e.end_angle)
        elif isinstance(e, PolylineEntity):
            e.vertices = [self._round_point(v) for v in e.vertices]
        elif isinstance(e, TextEntity):
            e.insert = self._round_point(e.insert)
            e.height = self._round_float(e.height)
        elif isinstance(e, DimensionEntity):
            e.defpoint = self._round_point(e.defpoint)
            e.text_midpoint = self._round_point(e.text_midpoint)
            e.measurement = self._round_float(e.measurement)
        
    def _explode_block(self, sub_entities: List[GeometryEntity], parent_block: BlockReference, 
                       parent_insert: Point, parent_rot: float, parent_sx: float, parent_sy: float) -> List[GeometryEntity]:
        result = []
        
        abs_sx = parent_sx * parent_block.scale_x
        abs_sy = parent_sy * parent_block.scale_y
        abs_rot = parent_rot + parent_block.rotation
        abs_insert = self._transform_point(parent_block.insert, parent_insert, parent_rot, parent_sx, parent_sy)

        # Track transform stack for provenance
        current_transform = {
            "insert": abs_insert.as_tuple(),
            "rotation": abs_rot,
            "scale_x": abs_sx,
            "scale_y": abs_sy
        }

        for sub_e in sub_entities:
            # Create a clone with a new UUID and updated provenance
            new_id = uuid.uuid4()
            base_kwargs = {
                "id": new_id,
                "layer": sub_e.layer,
                "color": sub_e.color,
                "source_entity_id": sub_e.source_entity_id,
                "source_block": sub_e.source_block,
                "source_layer": sub_e.source_layer,
                "transform_stack": parent_block.transform_stack + [current_transform],
                "parent_block": str(parent_block.id),
                "metadata": sub_e.metadata.copy()
            }
            
            if isinstance(sub_e, BlockReference):
                new_block = BlockReference(
                    **base_kwargs,
                    name=sub_e.name,
                    insert=sub_e.insert,
                    rotation=sub_e.rotation,
                    scale_x=sub_e.scale_x,
                    scale_y=sub_e.scale_y,
                    scale_z=sub_e.scale_z,
                    children=[]
                )
                self.repo.add(new_block)
                result.append(new_block)
                
                nested_sub = sub_e.metadata.get("_parsed_entities", [])
                children = self._explode_block(nested_sub, new_block, abs_insert, abs_rot, abs_sx, abs_sy)
                new_block.children = [c.id for c in children]
                
            elif isinstance(sub_e, LineEntity):
                new_e = LineEntity(
                    **base_kwargs,
                    start=self._transform_point(sub_e.start, abs_insert, abs_rot, abs_sx, abs_sy),
                    end=self._transform_point(sub_e.end, abs_insert, abs_rot, abs_sx, abs_sy)
                )
                self.repo.add(new_e)
                result.append(new_e)
                
            elif isinstance(sub_e, ArcEntity):
                new_e = ArcEntity(
                    **base_kwargs,
                    center=self._transform_point(sub_e.center, abs_insert, abs_rot, abs_sx, abs_sy),
                    radius=self._round_float(sub_e.radius * abs_sx),
                    start_angle=self._round_float(sub_e.start_angle + abs_rot),
                    end_angle=self._round_float(sub_e.end_angle + abs_rot)
                )
                self.repo.add(new_e)
                result.append(new_e)
                
            elif isinstance(sub_e, PolylineEntity):
                new_vertices = [self._transform_point(v, abs_insert, abs_rot, abs_sx, abs_sy) for v in sub_e.vertices]
                new_e = PolylineEntity(
                    **base_kwargs,
                    vertices=new_vertices,
                    is_closed=sub_e.is_closed
                )
                self.repo.add(new_e)
                result.append(new_e)
                
            elif isinstance(sub_e, TextEntity):
                new_e = TextEntity(
                    **base_kwargs,
                    insert=self._transform_point(sub_e.insert, abs_insert, abs_rot, abs_sx, abs_sy),
                    text=sub_e.text,
                    height=self._round_float(sub_e.height * abs_sy)
                )
                self.repo.add(new_e)
                result.append(new_e)
                
            elif isinstance(sub_e, DimensionEntity):
                new_e = DimensionEntity(
                    **base_kwargs,
                    defpoint=self._transform_point(sub_e.defpoint, abs_insert, abs_rot, abs_sx, abs_sy),
                    text_midpoint=self._transform_point(sub_e.text_midpoint, abs_insert, abs_rot, abs_sx, abs_sy),
                    measurement=self._round_float(sub_e.measurement * abs_sx),
                    text=sub_e.text
                )
                self.repo.add(new_e)
                result.append(new_e)
                
        return result
