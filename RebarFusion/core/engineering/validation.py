from dataclasses import dataclass
from typing import Dict, List
from uuid import UUID

@dataclass
class QAWarning:
    severity: str           # 'CRITICAL', 'WARNING'
    rule_name: str
    message: str
    object_uuid: UUID

class EngineeringQAValidator:
    """
    Phase 8.5: Engineering QA Validation
    Analyzes generated Engineering Objects for logical inconsistencies, orphans, and conflicts.

    Ownership boundary: this validator checks each EngineeringObject in
    isolation (missing/conflicting parameters on that one object). It does
    NOT check for the same mark appearing on multiple objects — that is
    expected and normal before Phase 9 groups same-mark bars into an
    EngineeringFamily (same mark + diameter + spacing + orientation = one
    family). A cross-object "two different families both claim mark X" check
    belongs in the Phase 9 family validator, not here. See
    `summarize_marks()` for a non-blocking, informational view of mark
    sharing at this phase instead.
    """

    def validate(self, eng_objects: dict) -> List[QAWarning]:
        warnings = []

        for comp_uuid, obj in eng_objects.items():
            if not hasattr(obj, 'object_type'):
                continue

            # QA Rule 1: Identity/Mark Traceability
            if obj.object_type == 'Bar':
                # Rule 2: Orphan constraints
                # Diameter or spacing exists without a mark
                if obj.mark is None:
                    if obj.diameter is not None or obj.spacing is not None:
                        warnings.append(QAWarning(
                            severity='WARNING',
                            rule_name='orphan_constraints',
                            message=f"Component {comp_uuid} has constraints (Dia={obj.diameter}, Spacing={obj.spacing}) but no Mark.",
                            object_uuid=obj.uuid
                        ))
                else:
                    # Rule 3: Incomplete parameters
                    if obj.diameter is None:
                        warnings.append(QAWarning(
                            severity='WARNING',
                            rule_name='missing_diameter',
                            message=f"Mark {obj.mark} is missing diameter.",
                            object_uuid=obj.uuid
                        ))
                    if obj.spacing is None:
                        warnings.append(QAWarning(
                            severity='WARNING',
                            rule_name='missing_spacing',
                            message=f"Mark {obj.mark} is missing spacing.",
                            object_uuid=obj.uuid
                        ))

        return warnings


def summarize_marks(eng_objects: dict) -> Dict[str, int]:
    """
    Informational, non-blocking view of how many EngineeringObjects share
    each mark at this phase. Multiple objects sharing a mark is expected —
    Phase 9 is responsible for grouping them into an EngineeringFamily and
    for flagging it as an error if two different families claim the same
    mark. This is reporting only; it never produces a QAWarning.
    """
    counts: Dict[str, int] = {}
    for obj in eng_objects.values():
        if getattr(obj, 'object_type', None) == 'Bar' and obj.mark is not None:
            counts[obj.mark] = counts.get(obj.mark, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
