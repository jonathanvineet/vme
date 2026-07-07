from dataclasses import dataclass
from typing import Any, List, Optional, Tuple
from uuid import UUID
import re

@dataclass
class AnnotationToken:
    token_type: str         # 'TOKEN_MARK', 'TOKEN_DIAMETER', 'TOKEN_SPACING', etc.
    value: Any              # "N5", 16, 150
    source_uuid: UUID       # Links back to raw TEXT/DIMENSION entity
    raw_text: str           # The substring matched

@dataclass
class Annotation:
    uuid: UUID
    annotation_type: str    # 'TEXT', 'MTEXT', 'DIMENSION', 'LEADER'
    text: str
    insertion: Tuple[float, float, float]
    bbox: Tuple[float, float, float, float]
    rotation: float
    layer: str
    source_entity_uuid: UUID
    measurement: Optional[float] = None  # Specific to DIMENSION
    p1: Optional[Tuple[float, float, float]] = None
    p2: Optional[Tuple[float, float, float]] = None

class AnnotationParser:
    """
    Semantic parser that breaks raw Annotation text into Engineering Tokens.
    """
    
    # Common regex patterns in structural drawings
    # Mark: N1, N5, B2, T1
    MARK_PATTERN = re.compile(r'\b([A-Z][0-9]{1,3})\b')
    
    # Diameter: Ø16, T16, Y16, H16, d16
    DIA_PATTERN = re.compile(r'([ØTYHd])\s*(\d{1,2})\b', re.IGNORECASE)
    
    # Spacing: 150 c/c, 200 C/C, @150, 150@150, 200mm C/C
    SPACING_PATTERN = re.compile(r'(?:@|c/c|C/C|cc)\s*(\d{2,3})\b|(\d{2,3})\s*(?:mm)?\s*(?:c/c|C/C|cc|@)', re.IGNORECASE)
    
    # Count: 2-, 4x, 10 -
    COUNT_PATTERN = re.compile(r'\b(\d{1,3})\s*[-xX]\s*')
    
    # Layers: 2-Layers, Bottom Layer, T1, B1
    LAYER_PATTERN = re.compile(r'(\d+)\s*[-]*\s*Layers|([TB][12])\b', re.IGNORECASE)

    def parse(self, annotation: Annotation) -> List[AnnotationToken]:
        tokens = []
        text = annotation.text
        source = annotation.uuid
        
        # Dimensions typically represent length directly if purely numeric, but can contain text tags (e.g. '<>\XT8@200mm C/C')
        if annotation.annotation_type == 'DIMENSION':
            if annotation.measurement and annotation.measurement > 0:
                tokens.append(AnnotationToken('TOKEN_LENGTH', annotation.measurement, source, str(annotation.measurement)))
            else:
                clean_text = text.replace(' ', '').replace('<>', '')
                if clean_text.isdigit():
                    tokens.append(AnnotationToken('TOKEN_LENGTH', float(clean_text), source, text))
            # DO NOT return early, let regex match spacing/diameter tags!
            
        # Parse Marks
        for match in self.MARK_PATTERN.finditer(text):
            mark = match.group(1)
            if mark.upper() not in ['T1', 'T2', 'B1', 'B2']:
                tokens.append(AnnotationToken('TOKEN_MARK', mark, source, match.group(0)))
            
        # Parse Diameter
        # T8 -> Diameter 8
        for match in self.DIA_PATTERN.finditer(text):
            dia = float(match.group(2))
            tokens.append(AnnotationToken('TOKEN_DIAMETER', dia, source, match.group(0)))
            
        # Parse Spacing
        # @200mm C/C -> Spacing 200
        for match in self.SPACING_PATTERN.finditer(text):
            val = match.group(1) if match.group(1) else match.group(2)
            if val:
                tokens.append(AnnotationToken('TOKEN_SPACING', float(val), source, match.group(0)))
            
        # Parse Count
        for match in self.COUNT_PATTERN.finditer(text):
            tokens.append(AnnotationToken('TOKEN_COUNT', int(match.group(1)), source, match.group(0)))
            
        return tokens
