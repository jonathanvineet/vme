from __future__ import annotations

import math
import uuid
from typing import Any, Dict, Iterable, List, Tuple

from core.reconstruction.models import AssemblyLayer, BoundingBox, CoordinateFrame, ReinforcementAssembly


class AssemblyBuilder:
    def build(self, families: Iterable[Any]) -> List[ReinforcementAssembly]:
        grouped: Dict[str, List[Any]] = {}
        for family in families:
            grouped.setdefault(self._assembly_type(family), []).append(family)

        assemblies = []
        for assembly_type, group in sorted(grouped.items()):
            frame = self._coordinate_frame(group)
            bbox = self._bounding_box(group)
            confidence = self._confidence(group)
            assembly_uuid = uuid.uuid5(
                uuid.NAMESPACE_URL,
                "|".join([assembly_type] + [str(f.uuid) for f in group]),
            )
            assemblies.append(
                ReinforcementAssembly(
                    uuid=assembly_uuid,
                    assembly_type=assembly_type,
                    families=group,
                    local_coordinate_system=frame,
                    bounding_box=bbox,
                    confidence=confidence,
                    layers=self._layers(assembly_uuid, group),
                )
            )
        return assemblies

    def _assembly_type(self, family: Any) -> str:
        family_type = getattr(family, "family_type", "UNKNOWN")
        if family_type in {"PRIMARY_MAIN", "SECONDARY_DISTRIBUTION"}:
            return "slab_bottom_mesh"
        if family_type == "STIRRUP":
            return "stirrups"
        if family_type == "EDGE":
            return "edge_reinforcement"
        return "unclassified_reinforcement"

    def _coordinate_frame(self, families: List[Any]) -> CoordinateFrame:
        primary = max(families, key=lambda f: getattr(f, "detected_count", 0))
        angle = math.radians(getattr(primary, "dominant_direction", getattr(primary, "orientation", 0.0)))
        u = (math.cos(angle), math.sin(angle), 0.0)
        v = (-math.sin(angle), math.cos(angle), 0.0)
        w = (0.0, 0.0, 1.0)
        bbox = self._bounding_box(families)
        origin = (
            (bbox.min_x + bbox.max_x) / 2.0,
            (bbox.min_y + bbox.max_y) / 2.0,
            (bbox.min_z + bbox.max_z) / 2.0,
        )
        thickness = max(0.0, 2.0 * self._max_diameter(families) + 40.0)
        return CoordinateFrame(origin=origin, u_axis=u, v_axis=v, w_axis=w, thickness=thickness, cover=40.0)

    def _layers(self, assembly_uuid, families: List[Any]) -> List[AssemblyLayer]:
        buckets: Dict[Tuple[str, str], List[Any]] = {}
        for family in families:
            name = self._layer_name(family)
            direction = getattr(family, "dominant_direction_label", "Unknown")
            buckets.setdefault((name, direction), []).append(family)

        layers = []
        for index, ((name, direction), group) in enumerate(sorted(buckets.items())):
            layer_uuid = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"assembly-layer|{assembly_uuid}|{name}|{direction}",
            )
            layers.append(
                AssemblyLayer(
                    uuid=layer_uuid,
                    name=name,
                    direction=direction,
                    family_uuids=[f.uuid for f in group],
                    z_offset=self._layer_z_offset(index, group),
                )
            )
        return layers

    def _layer_name(self, family: Any) -> str:
        family_type = getattr(family, "family_type", "UNKNOWN")
        if family_type == "PRIMARY_MAIN":
            return "Layer 1 - Main"
        if family_type == "SECONDARY_DISTRIBUTION":
            return "Layer 2 - Distribution"
        if family_type == "STIRRUP":
            return "Stirrups"
        if family_type == "EDGE":
            return "Edge"
        return "Unclassified"

    def _layer_z_offset(self, index: int, families: List[Any]) -> float:
        return index * self._max_diameter(families)

    def _bounding_box(self, families: List[Any]) -> BoundingBox:
        boxes = []
        for family in families:
            for member in getattr(family, "members", []):
                boxes.append(member.bbox)

        if not boxes:
            return BoundingBox(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        return BoundingBox(
            min_x=min(bb[0] for bb in boxes),
            min_y=min(bb[1] for bb in boxes),
            min_z=0.0,
            max_x=max(bb[2] for bb in boxes),
            max_y=max(bb[3] for bb in boxes),
            max_z=0.0,
        )

    def _confidence(self, families: List[Any]) -> float:
        if not families:
            return 0.0
        return round(sum(getattr(f, "confidence", 0.0) for f in families) / len(families), 3)

    def _max_diameter(self, families: List[Any]) -> float:
        return max((float(getattr(f, "diameter", 0.0) or 12.0) for f in families), default=12.0)
