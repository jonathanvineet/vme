from dataclasses import dataclass, field
from typing import Dict, List, Any
from uuid import UUID

@dataclass
class Evidence:
    rule_name: str
    passed: bool
    description: str

@dataclass
class RecognitionResult:
    component_uuid: UUID
    label: str
    confidence: float
    recognizer: str
    evidence: List[Evidence] = field(default_factory=list)
    measurements: Dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
