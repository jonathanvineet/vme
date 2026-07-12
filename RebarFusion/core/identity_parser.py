import re
import uuid
from core.project import DrawingIdentity

# Fixed namespace so a drawing's identity UUID — and everything derived from
# it downstream (canonical entity IDs, edges, components) — is a pure
# function of the filename, not a fresh random value on every project load.
# A uuid4() here would make every entity ID in the pipeline nondeterministic
# across runs on identical input, which is what caused Phase 6/7 output
# (component statistics, recognition fingerprints) to drift run-to-run.
NAMESPACE_IDENTITY = uuid.UUID('a1b53f2e-6c1d-4a3f-9c4e-2f8b6d7a5e11')

def parse_identity(filename: str) -> DrawingIdentity:
    """
    Extracts DrawingIdentity from standard filename conventions.
    Format: Element-Floor-Number(View)
    e.g., PW-GF-02(M1)
    """
    basename = filename.split('.')[0].strip()
    identity_uuid = uuid.uuid5(NAMESPACE_IDENTITY, filename)

    # Try the standard format: Element-Floor-Number(View)
    # e.g., PW-GF-02(M1)
    match = re.match(r"^([A-Za-z]+)-([A-Za-z0-9]+)-(\d+)\(([^)]+)\)$", basename)

    if match:
        element, floor, number, view = match.groups()
        return DrawingIdentity(
            uuid=identity_uuid,
            drawing_number=f"{element}-{floor}-{number}",
            view=view,
            floor=floor,
            element=element,
            revision="Unknown",
            confidence=0.8  # High confidence based on explicit filename match
        )

    # Fallback to generic parsing
    return DrawingIdentity(
        uuid=identity_uuid,
        drawing_number=basename,
        view="Unknown",
        floor="Unknown",
        element="Unknown",
        revision="Unknown",
        confidence=0.2
    )
