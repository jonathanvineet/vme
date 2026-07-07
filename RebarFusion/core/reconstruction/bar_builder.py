from __future__ import annotations

import math
import uuid
from typing import Any, List

from core.reconstruction.adjustments import ReinforcementAdjuster
from core.reconstruction.models import BarPath, PhysicalBar, ReinforcementAssembly


class PhysicalBarBuilder:
    def __init__(self, adjuster: ReinforcementAdjuster | None = None):
        self.adjuster = adjuster or ReinforcementAdjuster()

    def build_for_assembly(self, assembly: ReinforcementAssembly) -> List[PhysicalBar]:
        bars: List[PhysicalBar] = []
        for family in assembly.families:
            layer = self._layer_for_family(assembly, family)
            for member in getattr(family, "members", []):
                bars.append(self._bar_from_member(assembly, family, member, layer))
        self._assign_bars_to_layers(assembly, bars)
        assembly.bars = bars
        return bars

    def _bar_from_member(self, assembly: ReinforcementAssembly, family: Any, member: Any, layer) -> PhysicalBar:
        angle = math.radians(getattr(family, "orientation", 0.0))
        ax, ay = math.cos(angle), math.sin(angle)
        half = getattr(family, "length", 0.0) / 2.0
        cx, cy = member.centroid
        raw_points = [
            (cx - ax * half, cy - ay * half, 0.0),
            (cx + ax * half, cy + ay * half, 0.0),
        ]
        family_uuid = family.uuid
        member_uuid = member.uuid
        bar_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"physical-bar|{family_uuid}|{member_uuid}")
        diameter = float(getattr(family, "diameter", 0.0) or 12.0)
        radius = diameter / 2.0
        centerline_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"bar-path|{family_uuid}|{member_uuid}")
        centerline = BarPath(
            uuid=centerline_uuid,
            family_uuid=family_uuid,
            member_uuid=member_uuid,
            points=raw_points,
            closed=getattr(family, "recognition_type", "") == "stirrup",
        )
        adjusted_centerline, adjustment_notes = self.adjuster.apply_layer_and_cover(
            centerline,
            assembly.local_coordinate_system,
            layer.z_offset if layer else self._z_for_family(family),
            radius,
        )
        return PhysicalBar(
            uuid=bar_uuid,
            family_uuid=family_uuid,
            member_uuid=member_uuid,
            mark=getattr(family, "mark", ""),
            diameter=diameter,
            radius=radius,
            centerline=adjusted_centerline,
            path=adjusted_centerline.points,
            bar_type=getattr(family, "recognition_type", "unknown"),
            layer_uuid=layer.uuid if layer else None,
            adjustment_notes=adjustment_notes,
            confidence=min(getattr(family, "confidence", 0.0), getattr(member, "confidence", 0.0)),
        )

    def _layer_for_family(self, assembly: ReinforcementAssembly, family: Any):
        for layer in assembly.layers:
            if family.uuid in layer.family_uuids:
                return layer
        return None

    def _assign_bars_to_layers(self, assembly: ReinforcementAssembly, bars: List[PhysicalBar]):
        by_layer = {}
        for bar in bars:
            if bar.layer_uuid:
                by_layer.setdefault(bar.layer_uuid, []).append(bar.uuid)
        for layer in assembly.layers:
            layer.bar_uuids = by_layer.get(layer.uuid, [])

    def _z_for_family(self, family: Any) -> float:
        family_type = getattr(family, "family_type", "")
        if family_type == "SECONDARY_DISTRIBUTION":
            return float(getattr(family, "diameter", 0.0) or 12.0)
        return 0.0
