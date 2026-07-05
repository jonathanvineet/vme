from typing import Dict, List, Optional
from uuid import UUID
from core.project import DrawingIdentity
from core.geometry.entities import (
    GeometryEntity, LineEntity, ArcEntity, PolylineEntity, 
    InsertEntity, TextEntity, MTextEntity, DimensionEntity, 
    HatchEntity, CircleEntity, UnknownEntity
)

class DrawingRepository:
    """
    Isolated geometry repository for a single drawing.
    """
    def __init__(self, identity: DrawingIdentity):
        self.identity = identity
        self.lines: List[LineEntity] = []
        self.arcs: List[ArcEntity] = []
        self.polylines: List[PolylineEntity] = []
        self.inserts: List[InsertEntity] = []
        self.texts: List[TextEntity] = []
        self.mtexts: List[MTextEntity] = []
        self.dimensions: List[DimensionEntity] = []
        self.hatches: List[HatchEntity] = []
        self.circles: List[CircleEntity] = []
        self.unknowns: List[UnknownEntity] = []
        
    def add(self, entity: GeometryEntity):
        if isinstance(entity, LineEntity): self.lines.append(entity)
        elif isinstance(entity, ArcEntity): self.arcs.append(entity)
        elif isinstance(entity, PolylineEntity): self.polylines.append(entity)
        elif isinstance(entity, InsertEntity): self.inserts.append(entity)
        elif isinstance(entity, TextEntity): self.texts.append(entity)
        elif isinstance(entity, MTextEntity): self.mtexts.append(entity)
        elif isinstance(entity, DimensionEntity): self.dimensions.append(entity)
        elif isinstance(entity, HatchEntity): self.hatches.append(entity)
        elif isinstance(entity, CircleEntity): self.circles.append(entity)
        elif isinstance(entity, UnknownEntity): self.unknowns.append(entity)
        else:
            self.unknowns.append(UnknownEntity(
                id=entity.id,
                dxf_type=entity.dxf_type,
                layer=entity.layer,
                color=entity.color,
                linetype=entity.linetype,
                handle=entity.handle,
                owner_handle=entity.owner_handle,
                parent_block=entity.parent_block,
                transform=entity.transform,
                bounding_box=entity.bounding_box,
                raw_properties=entity.raw_properties,
                raw_data="Unclassified GeometryEntity type"
            ))

    def generate_translation_report(self) -> Dict[str, int]:
        return {
            "LINE": len(self.lines),
            "ARC": len(self.arcs),
            "POLYLINE": len(self.polylines),
            "INSERT": len(self.inserts),
            "TEXT": len(self.texts),
            "MTEXT": len(self.mtexts),
            "DIMENSION": len(self.dimensions),
            "HATCH": len(self.hatches),
            "CIRCLE": len(self.circles),
            "UNKNOWN": len(self.unknowns)
        }

class ProjectRepository:
    """
    Root repository holding geometry for all parsed drawings in a project.
    """
    def __init__(self):
        self.drawings: Dict[UUID, DrawingRepository] = {}
        
    def add_drawing(self, repo: DrawingRepository):
        self.drawings[repo.identity.uuid] = repo
        
    def get_drawing(self, identity_uuid: UUID) -> Optional[DrawingRepository]:
        return self.drawings.get(identity_uuid)
