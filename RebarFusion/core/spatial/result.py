from dataclasses import dataclass
from core.geometry.canonical import CanonicalEntity

@dataclass
class QueryResult:
    entity: CanonicalEntity
    distance: float
    index_used: str
