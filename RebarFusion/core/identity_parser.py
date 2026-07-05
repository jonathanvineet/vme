import re
import uuid
from core.project import DrawingIdentity

def parse_identity(filename: str) -> DrawingIdentity:
    """
    Extracts DrawingIdentity from standard filename conventions.
    Format: Element-Floor-Number(View)
    e.g., PW-GF-02(M1)
    """
    basename = filename.split('.')[0].strip()
    
    # Try the standard format: Element-Floor-Number(View)
    # e.g., PW-GF-02(M1)
    match = re.match(r"^([A-Za-z]+)-([A-Za-z0-9]+)-(\d+)\(([^)]+)\)$", basename)
    
    if match:
        element, floor, number, view = match.groups()
        return DrawingIdentity(
            uuid=uuid.uuid4(),
            drawing_number=f"{element}-{floor}-{number}",
            view=view,
            floor=floor,
            element=element,
            revision="Unknown",
            confidence=0.8  # High confidence based on explicit filename match
        )
    
    # Fallback to generic parsing
    return DrawingIdentity(
        uuid=uuid.uuid4(),
        drawing_number=basename,
        view="Unknown",
        floor="Unknown",
        element="Unknown",
        revision="Unknown",
        confidence=0.2
    )
