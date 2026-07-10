from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import math
import uuid

from core.topology.graph import ConnectivityGraph, ConnectedComponent
from core.spatial.engine import SpatialQueryEngine
from core.engineering.models import Evidence


@dataclass
class EngineeringMember:
    uuid: UUID
    component_uuid: UUID
    length: float
    orientation: float
    layer: str
    bbox: Tuple[float, float, float, float]
    centroid: Tuple[float, float]
    offset_from_representative: float
    confidence: float


@dataclass
class FamilyQA:
    expected_members: Optional[int]
    found_members: int
    missing_members: Optional[int]
    confidence: float
    missing_offsets: List[float] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class EngineeringFamily:
    uuid: UUID
    mark: str
    diameter: float
    spacing: float
    annotated_spacing: float
    inferred_spacing: float
    spacing_source: str
    spacing_confidence: float
    average_spacing_error: float
    length: float
    orientation: float
    dominant_direction: float
    dominant_direction_label: str
    normal_direction: float
    normal_direction_label: str
    layer: str
    recognition_type: str
    family_type: str
    representative_component: UUID
    representative_component_uuid: UUID
    member_components: List[UUID] = field(default_factory=list)
    members: List[EngineeringMember] = field(default_factory=list)
    member_component_uuids: List[UUID] = field(default_factory=list)
    expected_members: Optional[int] = None
    detected_count: int = 0
    estimated_count: int = 0
    inferred_count: int = 0
    inferred_span: float = 0.0
    confidence: float = 0.0
    missing_member_offsets: List[float] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    rejected_candidates: List[Dict[str, Any]] = field(default_factory=list)
    qa: Optional[FamilyQA] = None


@dataclass
class _ComponentProfile:
    component_uuid: UUID
    layer: str
    length: float
    orientation: float
    recognition_type: str
    bbox: Tuple[float, float, float, float]
    centroid: Tuple[float, float]
    axis_center: float
    perp_center: float


class FamilyBuilder:
    def __init__(self, graph: ConnectivityGraph, comp_repo, spatial_engine: SpatialQueryEngine, recognition_cache=None):
        self.graph = graph
        self.comp_repo = comp_repo
        self.spatial = spatial_engine
        self.recognition_cache = recognition_cache
        self._profiles: Dict[UUID, _ComponentProfile] = {}

    def build_families(self, eng_bars: Dict[UUID, Any]) -> List[EngineeringFamily]:
        seeds = self._seed_bars(eng_bars)
        grouped = self._group_family_seeds(seeds)
        
        families = []
        for seed_group in grouped:
            remaining_seeds = list(seed_group)
            while remaining_seeds:
                fam = self._build_family(remaining_seeds)
                families.append(fam)
                
                # Remove seeds that were successfully captured as members of this family
                captured_uuids = set(fam.member_component_uuids)
                
                # Also ensure we remove the representative component so we don't infinite loop
                captured_uuids.add(fam.representative_component_uuid)
                
                remaining_seeds = [s for s in remaining_seeds if s[0] not in captured_uuids]
                
        families = self._dedupe_families(families)

        for family in families:
            family.qa = self._build_qa(family)

        return sorted(families, key=lambda f: (f.mark, f.layer, str(f.uuid)))

    def _seed_bars(self, eng_bars: Dict[UUID, Any]) -> Dict[UUID, Any]:
        seeds = {
            comp_uuid: bar
            for comp_uuid, bar in eng_bars.items()
            if getattr(bar, "mark", None) and comp_uuid in self.comp_repo.components
        }

        mark_props: Dict[str, Dict[str, float]] = {}
        shape_props: Dict[Tuple[str, int], Dict[str, float]] = {}
        for comp_uuid, bar in eng_bars.items():
            mark = getattr(bar, "mark", None)
            dia = getattr(bar, "diameter", None) or 0.0
            spacing = getattr(bar, "spacing", None) or 0.0
            if mark:
                props = mark_props.setdefault(mark, {"diameter": 0.0, "spacing": 0.0})
                props["diameter"] = max(props["diameter"], float(dia))
                props["spacing"] = max(props["spacing"], float(spacing))

            profile = self._profile(comp_uuid)
            if profile and (dia or spacing):
                key = (profile.layer, round(profile.length / 50.0))
                props = shape_props.setdefault(key, {"diameter": 0.0, "spacing": 0.0})
                props["diameter"] = max(props["diameter"], float(dia))
                props["spacing"] = max(props["spacing"], float(spacing))

        # Diameter/spacing tokens are sometimes associated with a sibling bar
        # rather than the marked representative. Propagate within each mark.
        for bar in seeds.values():
            props = mark_props.get(bar.mark, {})
            if not getattr(bar, "diameter", None) and props.get("diameter", 0.0) > 0:
                bar.diameter = props["diameter"]
            if not getattr(bar, "spacing", None) and props.get("spacing", 0.0) > 0:
                bar.spacing = props["spacing"]

        for comp_uuid, bar in sorted(seeds.items(), key=lambda item: str(item[0])):
            profile = self._profile(comp_uuid)
            if not profile:
                continue
            props = shape_props.get((profile.layer, round(profile.length / 50.0)), {})
            if not getattr(bar, "diameter", None) and props.get("diameter", 0.0) > 0:
                bar.diameter = props["diameter"]
            if not getattr(bar, "spacing", None) and props.get("spacing", 0.0) > 0:
                bar.spacing = props["spacing"]

        return seeds

    def _group_family_seeds(self, seeds: Dict[UUID, Any]) -> List[List[Tuple[UUID, Any, _ComponentProfile]]]:
        groups: Dict[Tuple[str, str, int, int], List[Tuple[UUID, Any, _ComponentProfile]]] = {}
        for comp_uuid, bar in seeds.items():
            profile = self._profile(comp_uuid)
            if not profile:
                continue
            key = (
                bar.mark,
                profile.layer,
                profile.recognition_type,
                round(profile.orientation / 10.0),
                round(profile.length / 100.0),
            )
            groups.setdefault(key, []).append((comp_uuid, bar, profile))
        return list(groups.values())

    def _build_family(self, seed_group: List[Tuple[UUID, Any, _ComponentProfile]]) -> EngineeringFamily:
        rep_uuid, rep_bar, rep_profile = max(seed_group, key=lambda item: (item[2].length, str(item[0])))
        diameters = [float(getattr(bar, "diameter", 0.0) or 0.0) for _, bar, _ in seed_group]
        spacings = [float(getattr(bar, "spacing", 0.0) or 0.0) for _, bar, _ in seed_group]
        counts = [getattr(bar, "expected_count", None) for _, bar, _ in seed_group if getattr(bar, "expected_count", None)]

        family = EngineeringFamily(
            uuid=self._stable_uuid("family-seed", rep_bar.mark, rep_profile.layer, rep_profile.component_uuid),
            mark=rep_bar.mark,
            diameter=max(diameters) if diameters else 0.0,
            spacing=max(spacings) if spacings else 0.0,
            annotated_spacing=max(spacings) if spacings else 0.0,
            inferred_spacing=0.0,
            spacing_source="annotation" if spacings and max(spacings) > 0 else "inferred",
            spacing_confidence=0.0,
            average_spacing_error=0.0,
            length=rep_profile.length,
            orientation=rep_profile.orientation,
            dominant_direction=rep_profile.orientation,
            dominant_direction_label=self._direction_label(rep_profile.orientation),
            normal_direction=(rep_profile.orientation + 90.0) % 180.0,
            normal_direction_label=self._direction_label((rep_profile.orientation + 90.0) % 180.0),
            layer=rep_profile.layer,
            recognition_type=rep_profile.recognition_type,
            family_type=self._classify_family_type(rep_profile.recognition_type, rep_profile.orientation, max(spacings) if spacings else 0.0),
            representative_component=rep_uuid,
            representative_component_uuid=rep_uuid,
            expected_members=max(counts) if counts else None,
        )
        self._discover_members(family, rep_profile)
        self._finalize_family(family)
        return family

    def _discover_members(self, family: EngineeringFamily, rep_profile: _ComponentProfile):
        candidates: List[Tuple[float, _ComponentProfile, float]] = [(0.0, rep_profile, 1.0)]

        for other_uuid in sorted(self.comp_repo.components, key=str):
            if other_uuid == family.representative_component_uuid:
                continue
            profile = self._profile(other_uuid)
            if not profile:
                continue
            if profile.layer != family.layer:
                self._record_rejection(family, profile, "different_layer", f"layer differs: {profile.layer} vs {family.layer}")
                continue
            if profile.recognition_type != family.recognition_type:
                self._record_rejection(
                    family,
                    profile,
                    "different_recognition_type",
                    f"recognition differs: {profile.recognition_type} vs {family.recognition_type}",
                )
                continue

            angle_diff = self._angle_diff(profile.orientation, family.orientation)
            if angle_diff > 5.0:
                self._record_rejection(family, profile, "different_orientation", f"orientation differs {angle_diff:.1f} degrees")
                continue

            if family.length > 0:
                length_diff = abs(profile.length - family.length) / family.length
                if length_diff > 0.05:
                    self._record_rejection(family, profile, "different_length", f"length differs {length_diff * 100:.1f}%")
                    continue
            else:
                length_diff = 0.0

            axis_tol = max(500.0, family.length * 0.25)
            axis_delta = abs(profile.axis_center - rep_profile.axis_center)
            if axis_delta > axis_tol:
                self._record_rejection(family, profile, "not_collinear", f"axis differs {axis_delta:.1f}mm")
                continue

            offset = profile.perp_center - rep_profile.perp_center
            if abs(offset) < 10.0:
                self._record_rejection(family, profile, "duplicate_or_too_close", f"offset {offset:.1f}mm is too close")
                continue

            confidence = max(0.0, 1.0 - (angle_diff / 5.0) * 0.25 - min(length_diff, 0.05) * 2.0)
            candidates.append((offset, profile, confidence))

        selected = self._select_spacing_sequence(candidates, family.spacing)
        selected.sort(key=lambda item: item[0])

        family.members = [
            EngineeringMember(
                uuid=self._stable_uuid("member", family.uuid, profile.component_uuid),
                component_uuid=profile.component_uuid,
                length=profile.length,
                orientation=profile.orientation,
                layer=profile.layer,
                bbox=profile.bbox,
                centroid=profile.centroid,
                offset_from_representative=offset,
                confidence=confidence,
            )
            for offset, profile, confidence in selected
        ]
        family.member_component_uuids = [m.component_uuid for m in family.members]

    def _select_spacing_sequence(
        self,
        candidates: List[Tuple[float, _ComponentProfile, float]],
        spacing: float,
    ) -> List[Tuple[float, _ComponentProfile, float]]:
        if spacing <= 0:
            return [item for item in candidates if abs(item[0]) <= 6000.0]

        tolerance = max(25.0, spacing * 0.35)
        
        sorted_candidates = sorted(candidates, key=lambda x: abs(x[0]))
        accepted_offsets = [0.0]
        selected = []
        
        for item in sorted_candidates:
            offset = item[0]
            
            if offset == 0.0:
                selected.append(item)
                continue
                
            nearest_accepted = min(accepted_offsets, key=lambda a: abs(offset - a))
            diff = abs(offset - nearest_accepted)
            
            if diff < 10.0:
                continue  # Skip likely duplicates
            
            multiple = diff / spacing
            remainder = abs(multiple - round(multiple))
            
            # Use distance to NEAREST accepted bar to prevent cumulative drift breaking the chain
            if remainder * spacing < tolerance:
                selected.append(item)
                accepted_offsets.append(offset)
                
        return selected

    def _dedupe_families(self, families: List[EngineeringFamily]) -> List[EngineeringFamily]:
        kept: List[EngineeringFamily] = []
        for family in sorted(families, key=lambda f: len(f.member_component_uuids), reverse=True):
            family_members = set(family.member_component_uuids)
            duplicate = False
            for existing in kept:
                if family.mark != existing.mark or family.layer != existing.layer:
                    continue
                existing_members = set(existing.member_component_uuids)
                overlap = len(family_members & existing_members)
                smaller = max(1, min(len(family_members), len(existing_members)))
                if overlap / smaller >= 0.65:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(family)
        return kept

    def _finalize_family(self, family: EngineeringFamily):
        family.members.sort(key=lambda m: m.offset_from_representative)
        family.member_component_uuids = [m.component_uuid for m in family.members]
        family.member_components = list(family.member_component_uuids)

        offsets = [m.offset_from_representative for m in family.members]
        span = max(offsets) - min(offsets) if len(offsets) > 1 else 0.0
        family.inferred_span = round(span, 3)
        family.detected_count = len(family.members)

        inferred_spacing, spacing_confidence, spacing_error = self._estimate_spacing(offsets, family.annotated_spacing)
        family.inferred_spacing = inferred_spacing
        family.spacing_confidence = spacing_confidence
        family.average_spacing_error = spacing_error

        if family.annotated_spacing <= 0 and inferred_spacing > 0:
            family.spacing = inferred_spacing
            family.spacing_source = "inferred"
        elif family.annotated_spacing > 0:
            family.spacing = family.annotated_spacing
            family.spacing_source = "annotation"

        spacing_for_count = family.inferred_spacing if family.inferred_spacing > 0 else family.spacing
        if spacing_for_count > 0 and family.inferred_span > 0:
            family.estimated_count = int(round(family.inferred_span / spacing_for_count)) + 1
        else:
            family.estimated_count = family.detected_count
        family.inferred_count = family.estimated_count

        family.missing_member_offsets = self._missing_offsets(offsets, spacing_for_count)
        member_conf = sum(m.confidence for m in family.members) / family.detected_count if family.detected_count else 0.0
        completeness = 1.0
        if family.expected_members:
            completeness = min(1.0, family.detected_count / family.expected_members)
        if family.estimated_count:
            completeness = min(completeness, family.detected_count / family.estimated_count)
        family.confidence = round(max(0.0, min(1.0, member_conf * spacing_confidence * completeness)), 3)

        family.uuid = self._stable_uuid(
            "family",
            family.mark,
            family.layer,
            family.recognition_type,
            round(family.orientation, 3),
            round(family.length, 3),
            ",".join(str(uid) for uid in family.member_component_uuids),
        )
        for member in family.members:
            member.uuid = self._stable_uuid("member", family.uuid, member.component_uuid)

        family.evidence = [
            Evidence(
                "seed_detection",
                1.0,
                f"Representative component {family.representative_component_uuid} seeded family {family.mark}",
                family.representative_component_uuid,
            ),
            Evidence(
                "parallel_member_search",
                member_conf,
                f"Detected {family.detected_count} same-layer {family.recognition_type} members within orientation/length tolerances",
                family.representative_component_uuid,
            ),
            Evidence(
                "spacing_estimation",
                spacing_confidence,
                f"Spacing {family.spacing:.1f}mm from {family.spacing_source}; average error {family.average_spacing_error:.2f}mm",
                family.representative_component_uuid,
            ),
        ]
        family.family_type = self._classify_family_type(family.recognition_type, family.dominant_direction, family.spacing)

    def _estimate_spacing(self, offsets: List[float], annotated_spacing: float) -> Tuple[float, float, float]:
        if len(offsets) < 2:
            return (annotated_spacing or 0.0, 0.0, 0.0)

        sorted_offsets = sorted(offsets)
        gaps = [
            sorted_offsets[i + 1] - sorted_offsets[i]
            for i in range(len(sorted_offsets) - 1)
            if sorted_offsets[i + 1] - sorted_offsets[i] > 10.0
        ]
        if not gaps:
            return (annotated_spacing or 0.0, 0.0, 0.0)

        inferred = self._median(gaps)
        spacing = annotated_spacing if annotated_spacing > 0 else inferred
        errors = [abs(gap - spacing) for gap in gaps]
        avg_error = sum(errors) / len(errors) if errors else 0.0
        confidence = max(0.0, min(1.0, 1.0 - (avg_error / max(spacing, 1.0))))
        return (round(inferred, 3), round(confidence, 3), round(avg_error, 3))

    def _missing_offsets(self, offsets: List[float], spacing: float) -> List[float]:
        if len(offsets) < 2 or spacing <= 0:
            return []

        sorted_offsets = sorted(offsets)
        start = sorted_offsets[0]
        end = sorted_offsets[-1]
        tolerance = max(25.0, spacing * 0.35)
        missing = []
        slot_count = int(round((end - start) / spacing))
        for slot in range(slot_count + 1):
            expected = start + slot * spacing
            if min(abs(offset - expected) for offset in sorted_offsets) > tolerance:
                missing.append(round(expected, 3))
        return missing

    def _build_qa(self, family: EngineeringFamily) -> FamilyQA:
        warnings: List[str] = []
        found = len(family.members)
        expected = family.expected_members
        missing = None

        if family.spacing <= 0:
            warnings.append("missing_spacing")
        if family.diameter <= 0:
            warnings.append("missing_diameter")
        if found <= 1:
            warnings.append("single_member_family")

        if expected is not None:
            missing = max(0, expected - found)
            if missing:
                warnings.append(f"missing_{missing}_members")
        elif family.estimated_count > found:
            missing = family.estimated_count - found
            warnings.append(f"inferred_missing_{missing}_members")

        if family.missing_member_offsets:
            warnings.append("spacing_gaps_detected")

        return FamilyQA(
            expected_members=expected,
            found_members=found,
            missing_members=missing,
            confidence=family.confidence,
            missing_offsets=family.missing_member_offsets,
            warnings=warnings,
        )

    def _profile(self, comp_uuid: UUID) -> Optional[_ComponentProfile]:
        if comp_uuid in self._profiles:
            return self._profiles[comp_uuid]

        comp = self.comp_repo.components.get(comp_uuid)
        if not comp or not comp.edge_ids:
            return None

        layer = ""
        weighted_x = 0.0
        weighted_y = 0.0
        total_edge_len = 0.0
        longest_edge_len = -1.0
        orientation = 0.0

        for edge_id in comp.edge_ids:
            edge = self.graph.edges.get(edge_id)
            if not edge:
                continue
            layer = layer or edge.layer
            n1 = self.graph.nodes.get(edge.start_node_uuid)
            n2 = self.graph.nodes.get(edge.end_node_uuid)
            if not n1 or not n2:
                continue

            x1, y1, _ = n1.position
            x2, y2, _ = n2.position
            edge_len = max(edge.length, math.hypot(x2 - x1, y2 - y1))
            mid_x = (x1 + x2) / 2.0
            mid_y = (y1 + y2) / 2.0
            weighted_x += mid_x * edge_len
            weighted_y += mid_y * edge_len
            total_edge_len += edge_len

            if edge_len > longest_edge_len:
                longest_edge_len = edge_len
                orientation = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0

        if total_edge_len > 0:
            cx = weighted_x / total_edge_len
            cy = weighted_y / total_edge_len
        else:
            bb = comp.bbox
            cx = (bb[0] + bb[2]) / 2.0
            cy = (bb[1] + bb[3]) / 2.0

        length = float(comp.statistics.get("total_length", 0.0))
        axis_rad = math.radians(orientation)
        ax, ay = math.cos(axis_rad), math.sin(axis_rad)
        px, py = -ay, ax

        recognition_type = "unknown"
        if self.recognition_cache:
            result = self.recognition_cache.get(comp_uuid)
            if result:
                recognition_type = result.label

        profile = _ComponentProfile(
            component_uuid=comp_uuid,
            layer=layer,
            length=length,
            orientation=orientation,
            recognition_type=recognition_type,
            bbox=comp.bbox,
            centroid=(cx, cy),
            axis_center=cx * ax + cy * ay,
            perp_center=cx * px + cy * py,
        )
        self._profiles[comp_uuid] = profile
        return profile

    def _record_rejection(self, family: EngineeringFamily, profile: _ComponentProfile, reason: str, detail: str):
        if len(family.rejected_candidates) >= 250:
            return
        family.rejected_candidates.append({
            "component": profile.component_uuid,
            "reason": reason,
            "detail": detail,
            "length": round(profile.length, 3),
            "orientation": round(profile.orientation, 3),
            "recognition_type": profile.recognition_type,
            "layer": profile.layer,
        })

    @staticmethod
    def _classify_family_type(recognition_type: str, orientation: float, spacing: float) -> str:
        if spacing > 0:
            return "PRIMARY_MAIN" if FamilyBuilder._is_horizontalish(orientation) else "SECONDARY_DISTRIBUTION"
        if recognition_type == "stirrup":
            return "STIRRUP"
        if recognition_type == "branch":
            return "EDGE"
        if recognition_type in {"u_bar", "l_bar"}:
            return "EDGE"
        if recognition_type == "straight_bar":
            return "EDGE"
        return "UNKNOWN"

    @staticmethod
    def _direction_label(angle: float) -> str:
        normalized = angle % 180.0
        if normalized <= 22.5 or normalized >= 157.5:
            return "Horizontal"
        if 67.5 <= normalized <= 112.5:
            return "Vertical"
        return "Diagonal"

    @staticmethod
    def _is_horizontalish(angle: float) -> bool:
        normalized = angle % 180.0
        return normalized <= 45.0 or normalized >= 135.0

    @staticmethod
    def _angle_diff(a: float, b: float) -> float:
        diff = abs(a - b) % 180.0
        return min(diff, 180.0 - diff)

    @staticmethod
    def _median(values: List[float]) -> float:
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0

    @staticmethod
    def _stable_uuid(*parts: Any) -> UUID:
        return uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(part) for part in parts))
