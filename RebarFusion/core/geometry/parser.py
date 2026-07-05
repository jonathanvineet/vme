import ezdxf
import uuid
from ezdxf.document import Drawing
from typing import List
from core.geometry.entities import (
    Point, GeometryEntity, LineEntity, ArcEntity, 
    PolylineEntity, BlockReference, TextEntity, DimensionEntity
)

class CADParser:
    def __init__(self):
        pass

    def parse_dxf(self, filepath: str) -> List[GeometryEntity]:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        return self._parse_entities(msp, doc, source_block=None)
        
    def _parse_entities(self, entity_container, doc: Drawing, source_block: str = None) -> List[GeometryEntity]:
        entities = []
        for e in entity_container:
            dxftype = e.dxftype()
            
            layer = e.dxf.layer if hasattr(e.dxf, 'layer') else "0"
            color = e.dxf.color if hasattr(e.dxf, 'color') else 256
            handle = e.dxf.handle if hasattr(e.dxf, 'handle') else None
            
            base_kwargs = {
                "id": uuid.uuid4(),
                "layer": layer,
                "color": color,
                "source_entity_id": handle,
                "source_block": source_block,
                "source_layer": layer,
                "transform_stack": [],
                "parent_block": None,
                "metadata": {"dxftype": dxftype}
            }
            
            if dxftype == "LINE":
                entities.append(LineEntity(
                    **base_kwargs,
                    start=Point(e.dxf.start.x, e.dxf.start.y, e.dxf.start.z),
                    end=Point(e.dxf.end.x, e.dxf.end.y, e.dxf.end.z)
                ))
            elif dxftype == "ARC":
                entities.append(ArcEntity(
                    **base_kwargs,
                    center=Point(e.dxf.center.x, e.dxf.center.y, e.dxf.center.z),
                    radius=e.dxf.radius,
                    start_angle=e.dxf.start_angle,
                    end_angle=e.dxf.end_angle
                ))
            elif dxftype in ("LWPOLYLINE", "POLYLINE"):
                vertices = []
                if dxftype == "LWPOLYLINE":
                    for v in e.vertices:
                        vertices.append(Point(v[0], v[1], 0.0))
                else:
                    for v in e.vertices:
                        vertices.append(Point(v.dxf.location.x, v.dxf.location.y, v.dxf.location.z))
                is_closed = e.is_closed
                entities.append(PolylineEntity(
                    **base_kwargs,
                    vertices=vertices,
                    is_closed=is_closed
                ))
            elif dxftype == "INSERT":
                block_name = e.dxf.name
                block_entities = []
                if block_name in doc.blocks:
                    block_def = doc.blocks[block_name]
                    # Parse block definition geometries
                    block_entities = self._parse_entities(block_def, doc, source_block=block_name)
                
                # Here we abuse the 'children' field temporarily to store parsed sub-entities.
                # The normalizer will flatten this.
                b = BlockReference(
                    **base_kwargs,
                    name=block_name,
                    insert=Point(e.dxf.insert.x, e.dxf.insert.y, e.dxf.insert.z),
                    rotation=e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0.0,
                    scale_x=e.dxf.xscale if hasattr(e.dxf, 'xscale') else 1.0,
                    scale_y=e.dxf.yscale if hasattr(e.dxf, 'yscale') else 1.0,
                    scale_z=e.dxf.zscale if hasattr(e.dxf, 'zscale') else 1.0,
                    children=[]
                )
                b.metadata["_parsed_entities"] = block_entities
                entities.append(b)
                
            elif dxftype in ("TEXT", "MTEXT"):
                text_val = e.dxf.text if dxftype == "TEXT" else e.text
                insert = e.dxf.insert
                height = getattr(e.dxf, 'height', getattr(e.dxf, 'char_height', 1.0))
                entities.append(TextEntity(
                    **base_kwargs,
                    insert=Point(insert.x, insert.y, insert.z),
                    text=text_val,
                    height=height
                ))
            elif dxftype == "DIMENSION":
                defpoint = getattr(e.dxf, "defpoint", None)
                text_midpoint = getattr(e.dxf, "text_midpoint", None)
                measurement = getattr(e.dxf, "actual_measurement", 0.0)
                text_val = getattr(e.dxf, "text", "")
                
                if defpoint and text_midpoint:
                    entities.append(DimensionEntity(
                        **base_kwargs,
                        defpoint=Point(defpoint.x, defpoint.y, defpoint.z),
                        text_midpoint=Point(text_midpoint.x, text_midpoint.y, text_midpoint.z),
                        measurement=measurement,
                        text=text_val
                    ))
        return entities
