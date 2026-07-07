import ezdxf
import uuid
from typing import Any, Optional
from core.readers.base import DrawingReader
from core.project import DrawingStatistics, DrawingCapabilities, DrawingRegistration, DrawingIdentity
from core.geometry.repository import DrawingRepository
from core.geometry.entities import (
    Point, Matrix44, LineEntity, ArcEntity, PolylineEntity, 
    InsertEntity, TextEntity, MTextEntity, DimensionEntity, 
    HatchEntity, CircleEntity, UnknownEntity
)

class DXFReader(DrawingReader):
    def can_read(self, path: str) -> bool:
        return path.lower().endswith('.dxf')
        
    def read_metadata(self, path: str) -> dict:
        doc = ezdxf.readfile(path)
        metadata = {}
        header = doc.header
        
        # INSUNITS map
        units_map = {0: "unitless", 1: "inch", 2: "foot", 4: "mm", 5: "cm", 6: "m"}
        insunits = header.get('$INSUNITS', 0)
        metadata['units'] = units_map.get(insunits, f"unknown_{insunits}")
        metadata['dxf_version'] = doc.dxfversion
        
        return metadata

    def read_statistics(self, path: str) -> DrawingStatistics:
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        stats = DrawingStatistics()
        
        counts = {}
        layer_counts = {}
        block_counts = {}
        
        for entity in msp:
            dxftype = entity.dxftype()
            counts[dxftype] = counts.get(dxftype, 0) + 1
            
            layer = entity.dxf.layer
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
            
            if dxftype == "INSERT":
                bname = entity.dxf.name
                block_counts[bname] = block_counts.get(bname, 0) + 1
                
        stats.entity_counts = counts
        
        sorted_layers = sorted(layer_counts.items(), key=lambda x: -x[1])
        stats.dominant_layers = [l[0] for l in sorted_layers[:5]]
        
        sorted_blocks = sorted(block_counts.items(), key=lambda x: -x[1])
        stats.dominant_blocks = [b[0] for b in sorted_blocks[:5]]
        
        extmin = doc.header.get('$EXTMIN', (0,0,0))
        extmax = doc.header.get('$EXTMAX', (0,0,0))
        stats.bounding_box = (extmin[0], extmin[1], extmax[0], extmax[1])
        stats.extents = (abs(extmax[0] - extmin[0]), abs(extmax[1] - extmin[1]))
        
        total_entities = sum(counts.values())
        area = stats.extents[0] * stats.extents[1]
        if area > 0:
            stats.entity_density = total_entities / area
            
        return stats

    def read_capabilities(self, path: str) -> DrawingCapabilities:
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        caps = DrawingCapabilities()
        
        caps.layers = len(doc.layers) > 1
        caps.blocks = len(doc.blocks) > 0
        
        for entity in msp:
            dxftype = entity.dxftype()
            if dxftype in ("LINE", "ARC", "LWPOLYLINE", "POLYLINE"):
                caps.geometry = True
            if dxftype == "DIMENSION":
                caps.dimensions = True
            if dxftype in ("TEXT", "MTEXT", "LEADER", "MULTILEADER"):
                caps.annotations = True
            if dxftype == "SPLINE":
                caps.splines = True
                
        for block in doc.blocks:
            if "schedule" in block.name.lower():
                caps.schedule = True
            if "section" in block.name.lower():
                caps.sections = True
                
        return caps

    def read_registration(self, path: str) -> DrawingRegistration:
        doc = ezdxf.readfile(path)
        header = doc.header
        
        reg = DrawingRegistration()
        insbase = header.get('$INSBASE', (0,0,0))
        reg.origin = insbase
        reg.confidence = 0.5 
        
        return reg

    def read_geometry(self, path: str, identity: DrawingIdentity) -> DrawingRepository:
        """
        Phase 2 Translation: Parses DWG/DXF geometry into our GeometryEntity format
        with extreme provenance.
        """
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        
        repo = DrawingRepository(identity)
        
        def _get_bbox(entity) -> tuple:
            # We can't efficiently compute accurate bbox for all entities without a rendering engine.
            # Ezdxf has some support, but we'll use basic fallbacks.
            # In a real heavy CAD engine, this would use ezdxf.bbox module.
            try:
                from ezdxf.bbox import extents
                e = extents([entity])
                if e.has_data:
                    return (e.extmin.x, e.extmin.y, e.extmax.x, e.extmax.y)
            except Exception:
                pass
            return (0.0, 0.0, 0.0, 0.0)
            
        # UUID namespace tied to this drawing so IDs are stable across runs
        DRAWING_NS = uuid.UUID(str(identity.uuid))

        def _deterministic_uuid(handle: str) -> uuid.UUID:
            return uuid.uuid5(DRAWING_NS, handle)

        def _build_base(entity, parent_block: Optional[str] = None):
            handle = entity.dxf.handle or ''
            return {
                "id": _deterministic_uuid(handle),
                "dxf_type": entity.dxftype(),
                "layer": entity.dxf.layer,
                "color": entity.dxf.color if entity.dxf.hasattr('color') else 256,
                "linetype": entity.dxf.linetype if entity.dxf.hasattr('linetype') else 'BYLAYER',
                "handle": handle,
                "owner_handle": entity.dxf.owner if entity.dxf.hasattr('owner') else '',
                "parent_block": parent_block,   # always set — None for top-level entities
                "transform": Matrix44(),
                "bounding_box": _get_bbox(entity),
                "raw_properties": {k: v for k, v in entity.dxf.all_existing_dxf_attribs().items()}
            }

        # Process the modelspace
        for entity in msp:
            dxftype = entity.dxftype()
            base = _build_base(entity)
            
            if dxftype == "LINE":
                repo.add(LineEntity(**base, start=Point(entity.dxf.start.x, entity.dxf.start.y, entity.dxf.start.z), end=Point(entity.dxf.end.x, entity.dxf.end.y, entity.dxf.end.z)))
            elif dxftype == "ARC":
                repo.add(ArcEntity(**base, center=Point(entity.dxf.center.x, entity.dxf.center.y, entity.dxf.center.z), radius=entity.dxf.radius, start_angle=entity.dxf.start_angle, end_angle=entity.dxf.end_angle))
            elif dxftype == "CIRCLE":
                repo.add(CircleEntity(**base, center=Point(entity.dxf.center.x, entity.dxf.center.y, entity.dxf.center.z), radius=entity.dxf.radius))
            elif dxftype == "LWPOLYLINE":
                points = [Point(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in entity.get_points(format='xyz')]
                repo.add(PolylineEntity(**base, vertices=points, is_closed=entity.is_closed))
            elif dxftype == "POLYLINE":
                points = [Point(v.dxf.location.x, v.dxf.location.y, v.dxf.location.z) for v in entity.vertices]
                repo.add(PolylineEntity(**base, vertices=points, is_closed=entity.is_closed))
            elif dxftype == "INSERT":
                repo.add(InsertEntity(**base, block_name=entity.dxf.name, insertion_point=Point(entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z), rotation=entity.dxf.rotation, scale_x=entity.dxf.xscale, scale_y=entity.dxf.yscale, scale_z=entity.dxf.zscale))
            elif dxftype == "TEXT":
                repo.add(TextEntity(**base, text=entity.dxf.text, insertion_point=Point(entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z), height=entity.dxf.height, rotation=entity.dxf.rotation))
            elif dxftype == "MTEXT":
                repo.add(MTextEntity(**base, text=entity.text, insertion_point=Point(entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z), char_height=entity.dxf.char_height, rotation=entity.dxf.get('rotation', 0.0)))
            elif dxftype == "DIMENSION":
                p1, p2, defpoint = (0.0,0.0,0.0), (0.0,0.0,0.0), (0.0,0.0,0.0)
                if hasattr(entity.dxf, 'defpoint'): defpoint = (entity.dxf.defpoint.x, entity.dxf.defpoint.y, entity.dxf.defpoint.z)
                if hasattr(entity.dxf, 'defpoint2'): p1 = (entity.dxf.defpoint2.x, entity.dxf.defpoint2.y, entity.dxf.defpoint2.z)
                if hasattr(entity.dxf, 'defpoint3'): p2 = (entity.dxf.defpoint3.x, entity.dxf.defpoint3.y, entity.dxf.defpoint3.z)
                text = entity.dxf.text if hasattr(entity.dxf, 'text') else ""
                try:
                    measurement = entity.get_measurement()
                except Exception:
                    measurement = 0.0
                repo.add(DimensionEntity(**base, text=text, measurement=measurement, defpoint=Point(*defpoint), p1=Point(*p1), p2=Point(*p2)))
            elif dxftype == "HATCH":
                repo.add(HatchEntity(**base, pattern_name=entity.dxf.pattern_name, solid=entity.dxf.solid_fill, paths=[]))
            else:
                repo.add(UnknownEntity(**base, raw_data=str(entity)))
                
        return repo
