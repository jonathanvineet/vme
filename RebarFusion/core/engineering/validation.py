from dataclasses import dataclass
from typing import List
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
    """
    
    def validate(self, eng_objects: dict) -> List[QAWarning]:
        warnings = []
        marks_seen = {}

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

                    # Rule 4: Duplicate Marks
                    if obj.mark in marks_seen:
                        warnings.append(QAWarning(
                            severity='CRITICAL',
                            rule_name='duplicate_mark',
                            message=f"Duplicate Mark '{obj.mark}' assigned to multiple components: {marks_seen[obj.mark]} and {comp_uuid}",
                            object_uuid=obj.uuid
                        ))
                    else:
                        marks_seen[obj.mark] = comp_uuid
                        
        return warnings
