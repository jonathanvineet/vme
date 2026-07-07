from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional
from uuid import UUID
from core.recognition.annotations import AnnotationToken

@dataclass
class SourceReference:
    drawing_uuid: UUID
    component_uuid: UUID
    view_type: str          # e.g., "PLAN", "SECTION"

@dataclass
class EngineeringObject:
    uuid: UUID
    object_type: str        # 'Bar', 'Mesh', 'Anchor', etc.
    sources: List[SourceReference] = field(default_factory=list)

@dataclass
class EngineeringBar(EngineeringObject):
    mark: Optional[str] = None
    diameter: Optional[float] = None
    spacing: Optional[float] = None
    length: Optional[float] = None
    shape: str = "unknown"

@dataclass
class Evidence:
    rule: str
    score: float
    explanation: str
    source_uuid: UUID

@dataclass
class AssociationCandidate:
    component_uuid: UUID
    token: AnnotationToken
    score: float
    evidence: List[Evidence] = field(default_factory=list)

class EngineeringConstraint(ABC):
    def __init__(self, token: AnnotationToken, component_uuid: UUID, confidence: float):
        self.token = token
        self.component_uuid = component_uuid
        self.confidence = confidence

    @abstractmethod
    def apply(self, obj: EngineeringObject):
        pass

class DiameterConstraint(EngineeringConstraint):
    def apply(self, obj: EngineeringObject):
        if isinstance(obj, EngineeringBar):
            obj.diameter = self.token.value

class SpacingConstraint(EngineeringConstraint):
    def apply(self, obj: EngineeringObject):
        if isinstance(obj, EngineeringBar):
            obj.spacing = self.token.value

class MarkConstraint(EngineeringConstraint):
    def apply(self, obj: EngineeringObject):
        if isinstance(obj, EngineeringBar):
            obj.mark = self.token.value

class LengthConstraint(EngineeringConstraint):
    def apply(self, obj: EngineeringObject):
        if isinstance(obj, EngineeringBar):
            obj.length = self.token.value

class CountConstraint(EngineeringConstraint):
    def apply(self, obj: EngineeringObject):
        # Could be used later for assembly
        pass
