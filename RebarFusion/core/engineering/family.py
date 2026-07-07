from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from uuid import UUID
import uuid
import math

from core.topology.graph import ConnectivityGraph, ConnectedComponent
from core.spatial.engine import SpatialQueryEngine

@dataclass
class EngineeringFamily:
    uuid: UUID
    mark: str
    diameter: float
    spacing: float
    length: float
    orientation: float       # Angle in degrees
    layer: str
    representative_component_uuid: UUID
    member_component_uuids: List[UUID] = field(default_factory=list)

class FamilyBuilder:
    def __init__(self, graph: ConnectivityGraph, comp_repo, spatial_engine: SpatialQueryEngine):
        self.graph = graph
        self.comp_repo = comp_repo
        self.spatial = spatial_engine

    def build_families(self, eng_bars: Dict[UUID, Any]) -> List[EngineeringFamily]:
        families = []
        
        for comp_uuid, bar in eng_bars.items():
            if not getattr(bar, 'mark', None):
                continue
                
            comp = self.comp_repo.components.get(comp_uuid)
            if not comp:
                continue
                
            # Get geometry properties
            length = float(comp.statistics.get('total_length', 0.0))
            
            # Find orientation (angle of first edge)
            angle = 0.0
            if comp.edge_ids:
                edge = self.graph.edges.get(comp.edge_ids[0])
                if edge:
                    # Compute angle of line
                    n1 = self.graph.nodes.get(edge.start_node_uuid)
                    n2 = self.graph.nodes.get(edge.end_node_uuid)
                    if n1 and n2:
                        dx = n2.position[0] - n1.position[0]
                        dy = n2.position[1] - n1.position[1]
                        angle = math.degrees(math.atan2(dy, dx)) % 180.0

            # Find layer
            layer = ""
            if comp.edge_ids:
                edge = self.graph.edges.get(comp.edge_ids[0])
                if edge:
                    layer = edge.layer

            # Create family
            fam = EngineeringFamily(
                uuid=uuid.uuid4(),
                mark=bar.mark,
                diameter=bar.diameter if bar.diameter else 0.0,
                spacing=bar.spacing if bar.spacing else 0.0,
                length=length,
                orientation=angle,
                layer=layer,
                representative_component_uuid=comp_uuid,
                member_component_uuids=[comp_uuid]
            )
            families.append(fam)
            
        # ── PASS 1: Cross-component property bridging ────────────────────────
        # Marks and spacing annotations are often on different bar instances.
        # Build a lookup from (layer, shape_label) -> best resolved {diameter, spacing}.
        # This lets marked bars inherit spacing from dimension-annotated bars of the same type.
        
        # First, collect what properties each solved bar has
        comp_shape_map: Dict[UUID, str] = {}
        comp_layer_map: Dict[UUID, str] = {}
        for comp_uuid, _ in eng_bars.items():
            comp = self.comp_repo.components.get(comp_uuid)
            if comp and comp.edge_ids:
                e = self.graph.edges.get(comp.edge_ids[0])
                if e:
                    comp_layer_map[comp_uuid] = e.layer
                    
        # Build shape_props: for each (layer, length_bucket) -> best (diameter, spacing)
        shape_props: Dict[tuple, Dict] = {}
        for comp_uuid, bar in eng_bars.items():
            dia = getattr(bar, 'diameter', None)
            spc = getattr(bar, 'spacing', None)
            if not (dia or spc):
                continue
            comp = self.comp_repo.components.get(comp_uuid)
            if not comp:
                continue
            layer = comp_layer_map.get(comp_uuid, '')
            length = float(comp.statistics.get('total_length', 0.0))
            length_bucket = round(length / 50) * 50  # bucket to nearest 50mm
            key = (layer, length_bucket)
            props = shape_props.setdefault(key, {'diameter': 0.0, 'spacing': 0.0})
            if dia and dia > props['diameter']:
                props['diameter'] = dia
            if spc and spc > props['spacing']:
                props['spacing'] = spc
            
        # ── PASS 2: Apply cross-component properties to families ─────────────
        for fam in families:
            if not (fam.diameter > 0 or fam.spacing > 0):
                comp = self.comp_repo.components.get(fam.representative_component_uuid)
                if comp:
                    layer = comp_layer_map.get(fam.representative_component_uuid, '')
                    length = float(comp.statistics.get('total_length', 0.0))
                    length_bucket = round(length / 50) * 50
                    key = (layer, length_bucket)
                    if key in shape_props:
                        props = shape_props[key]
                        if props['diameter'] > 0:
                            fam.diameter = props['diameter']
                        if props['spacing'] > 0:
                            fam.spacing = props['spacing']
                    
        # ── PASS 3: Global mark-based propagation ────────────────────────────
        # Share best resolved properties across all families with the same mark
        mark_props: Dict[str, Dict] = {}
        for fam in families:
            if fam.mark:
                props = mark_props.setdefault(fam.mark, {'diameter': 0.0, 'spacing': 0.0})
                if fam.diameter > props['diameter']:
                    props['diameter'] = fam.diameter
                if fam.spacing > props['spacing']:
                    props['spacing'] = fam.spacing
                    
        for fam in families:
            if fam.mark and fam.mark in mark_props:
                props = mark_props[fam.mark]
                if props['diameter'] > 0:
                    fam.diameter = props['diameter']
                if props['spacing'] > 0:
                    fam.spacing = props['spacing']
                    
        # ── PASS 4: Member discovery with resolved spacing ───────────────────
        for fam in families:
            comp = self.comp_repo.components.get(fam.representative_component_uuid)
            if comp:
                self._discover_members(fam, comp)
                    
        return families


    def _discover_members(self, family: EngineeringFamily, rep_comp: ConnectedComponent):
        # Perpendicular search direction
        rad = math.radians(family.orientation + 90.0)
        px, py = math.cos(rad), math.sin(rad)
        
        # Centroid of representative component
        bb = rep_comp.bbox
        cx = (bb[0] + bb[2]) / 2.0
        cy = (bb[1] + bb[3]) / 2.0
        
        # Gather all candidate components: same layer, same length (within 15%), same angle
        candidates = []
        for other_uuid, other_comp in self.comp_repo.components.items():
            if other_uuid == family.representative_component_uuid:
                continue
                
            # Filter by layer
            other_layer = ""
            if other_comp.edge_ids:
                other_edge = self.graph.edges.get(other_comp.edge_ids[0])
                if other_edge:
                    other_layer = other_edge.layer
            if other_layer != family.layer:
                continue
                
            # Check length similarity (within 15%)
            o_len = other_comp.statistics.get('total_length', 0.0)
            if family.length > 0 and abs(o_len - family.length) / family.length > 0.15:
                continue
                
            # Check angle similarity (within 8 degrees)
            o_angle = 0.0
            if other_comp.edge_ids:
                edge = self.graph.edges.get(other_comp.edge_ids[0])
                if edge:
                    n1 = self.graph.nodes.get(edge.start_node_uuid)
                    n2 = self.graph.nodes.get(edge.end_node_uuid)
                    if n1 and n2:
                        ddx = n2.position[0] - n1.position[0]
                        ddy = n2.position[1] - n1.position[1]
                        o_angle = math.degrees(math.atan2(ddy, ddx)) % 180.0
                        
            angle_diff = abs(o_angle - family.orientation)
            angle_diff = min(angle_diff, 180.0 - angle_diff)
            if angle_diff > 8.0:
                continue
            
            # Compute centroid and perpendicular distance
            obb = other_comp.bbox
            ocx = (obb[0] + obb[2]) / 2.0
            ocy = (obb[1] + obb[3]) / 2.0
            ddx = ocx - cx
            ddy = ocy - cy
            perp_dist = abs(ddx * px + ddy * py)
            
            candidates.append((perp_dist, other_uuid))
        
        if not candidates:
            return
            
        # Sort candidates by perpendicular distance
        candidates.sort(key=lambda x: x[0])
        
        if family.spacing > 0:
            # Use spacing-relative check: allow ±30% of annotated spacing per nearest-neighbor hop
            # This avoids accumulated drift issues by checking per-step rather than from origin
            tol_abs = family.spacing * 0.35  # 35% tolerance on spacing
            
            # Add by checking if any bar is approximately at a spacing multiple FROM THE NEAREST ACCEPTED BAR
            accepted_perps = [0.0]  # rep comp is at 0
            for perp_dist, other_uuid in candidates:
                # Find nearest accepted bar's perp distance
                nearest_step = min(abs(perp_dist - a) for a in accepted_perps)
                if nearest_step < tol_abs:
                    # Too close — likely the same bar drawn twice (skip)
                    if nearest_step < 10.0:
                        continue
                    family.member_component_uuids.append(other_uuid)
                    accepted_perps.append(perp_dist)
                elif nearest_step < family.spacing + tol_abs:
                    # Approximately one spacing-step away
                    family.member_component_uuids.append(other_uuid)
                    accepted_perps.append(perp_dist)
        else:
            # No spacing: accept all parallel bars within 6000mm
            for perp_dist, other_uuid in candidates:
                if perp_dist < 6000.0:
                    family.member_component_uuids.append(other_uuid)

