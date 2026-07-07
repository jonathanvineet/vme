from typing import Dict, List
from uuid import UUID
import uuid

from core.engineering.models import EngineeringObject, EngineeringBar, EngineeringConstraint

class ConstraintSolver:
    """
    Groups constraints by component, resolves conflicting constraints,
    and builds EngineeringObjects.
    """
    def __init__(self):
        self.constraints: List[EngineeringConstraint] = []
        
    def add_constraint(self, constraint: EngineeringConstraint):
        self.constraints.append(constraint)
        
    def solve(self) -> Dict[UUID, EngineeringObject]:
        # Group constraints by target component
        by_component: Dict[UUID, List[EngineeringConstraint]] = {}
        for c in self.constraints:
            by_component.setdefault(c.component_uuid, []).append(c)
            
        objects: Dict[UUID, EngineeringObject] = {}
        
        for comp_uuid, constraints in by_component.items():
            # Create a base EngineeringBar for this component
            # (In a real system, you might determine object_type based on the component's shape)
            obj = EngineeringBar(
                uuid=uuid.uuid4(),
                object_type="Bar"
            )
            # Add source reference placeholder (drawing/view info would be injected later)
            
            # Sort constraints by confidence (highest first)
            # So if two conflicting diameter constraints exist, the more confident one wins
            sorted_c = sorted(constraints, key=lambda x: x.confidence, reverse=True)
            
            applied_types = set()
            for c in sorted_c:
                c_type = type(c)
                if c_type not in applied_types:
                    c.apply(obj)
                    applied_types.add(c_type)
                    
            objects[comp_uuid] = obj
            
        return objects
