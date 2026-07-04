import uuid
from typing import Dict, List, Optional
from core.geometry import (
    GeometryEntity, LineEntity, ArcEntity, PolylineEntity, 
    TextEntity, DimensionEntity, BlockReference
)

class GeometryRepository:
    """
    Central repository for all geometry entities.
    Provides fast queries and maintains references by UUID.
    """
    def __init__(self):
        self.entities: Dict[uuid.UUID, GeometryEntity] = {}
        
        self.lines: Dict[uuid.UUID, LineEntity] = {}
        self.arcs: Dict[uuid.UUID, ArcEntity] = {}
        self.polylines: Dict[uuid.UUID, PolylineEntity] = {}
        self.texts: Dict[uuid.UUID, TextEntity] = {}
        self.dimensions: Dict[uuid.UUID, DimensionEntity] = {}
        self.blocks: Dict[uuid.UUID, BlockReference] = {}

    def add(self, entity: GeometryEntity):
        self.entities[entity.id] = entity
        
        if isinstance(entity, LineEntity):
            self.lines[entity.id] = entity
        elif isinstance(entity, ArcEntity):
            self.arcs[entity.id] = entity
        elif isinstance(entity, PolylineEntity):
            self.polylines[entity.id] = entity
        elif isinstance(entity, TextEntity):
            self.texts[entity.id] = entity
        elif isinstance(entity, DimensionEntity):
            self.dimensions[entity.id] = entity
        elif isinstance(entity, BlockReference):
            self.blocks[entity.id] = entity

    def get(self, entity_id: uuid.UUID) -> Optional[GeometryEntity]:
        return self.entities.get(entity_id)

    def remove(self, entity_id: uuid.UUID):
        if entity_id not in self.entities:
            return
            
        entity = self.entities.pop(entity_id)
        
        if isinstance(entity, LineEntity):
            self.lines.pop(entity.id, None)
        elif isinstance(entity, ArcEntity):
            self.arcs.pop(entity.id, None)
        elif isinstance(entity, PolylineEntity):
            self.polylines.pop(entity.id, None)
        elif isinstance(entity, TextEntity):
            self.texts.pop(entity.id, None)
        elif isinstance(entity, DimensionEntity):
            self.dimensions.pop(entity.id, None)
        elif isinstance(entity, BlockReference):
            self.blocks.pop(entity.id, None)
            
    def get_all(self) -> List[GeometryEntity]:
        return list(self.entities.values())
