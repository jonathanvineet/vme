from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional

from core.reconstruction.adjustments import ReinforcementAdjuster
from core.reconstruction.geometry_recovery import recover_bar_path
from core.reconstruction.models import BarPath, PhysicalBar, ReinforcementAssembly

# Never presented as if it were real annotation data (see PhysicalBar.diameter_source):
# used only so a bar with no diameter annotation still has *something* to
# sweep a mesh from, so the viewer has a visible (but honestly-flagged)
# object rather than nothing at all.
UNKNOWN_DIAMETER_VISUAL_MM = 12.0


class PhysicalBarBuilder:
    def __init__(self, adjuster: ReinforcementAdjuster | None = None):
        self.adjuster = adjuster or ReinforcementAdjuster()

    def build_for_assembly(self, assembly: ReinforcementAssembly, graph=None,
                            entity_by_geom_id: Optional[Dict] = None, comp_repo=None) -> List[PhysicalBar]:
        bars: List[PhysicalBar] = []
        for family in assembly.families:
            layer = self._layer_for_family(assembly, family)
            rep_path = self._representative_path(family, graph, entity_by_geom_id, comp_repo)
            for member in getattr(family, "members", []):
                bars.append(self._bar_from_member(assembly, family, member, layer, rep_path))
        self._assign_bars_to_layers(assembly, bars)
        assembly.bars = bars
        return bars

    def _representative_path(self, family: Any, graph, entity_by_geom_id, comp_repo):
        """
        Phase 10B: recover the representative member's actual centerline
        from its recognized component geometry, instead of approximating a
        straight line from family.length/orientation (see
        docs/audits/phase10/10.0_reconstruction_audit.md). Falls back to
        the old straight-line approximation only if graph/component data
        isn't available (e.g. re-running against a stale Phase 9 JSON
        snapshot with no live graph) -- that fallback is flagged via
        recovery_method='fallback_straight' either way, never silently.
        """
        rep_uuid = getattr(family, "representative_component_uuid", None)
        if graph is not None and entity_by_geom_id is not None and comp_repo is not None and rep_uuid is not None:
            component = comp_repo.components.get(rep_uuid)
            if component is not None:
                recovered = recover_bar_path(component, graph, entity_by_geom_id)
                return recovered

        # Fallback: no live geometry available -- synthesize a straight
        # line as before, but mark it honestly rather than pretending it's
        # a recovered path.
        angle = math.radians(getattr(family, "orientation", 0.0))
        ax, ay = math.cos(angle), math.sin(angle)
        half = getattr(family, "length", 0.0) / 2.0
        rep = family.members[0] if getattr(family, "members", None) else None
        cx, cy = rep.centroid if rep else (0.0, 0.0)
        from core.reconstruction.geometry_recovery import RecoveredPath
        return RecoveredPath(
            points=[(cx - ax * half, cy - ay * half, 0.0), (cx + ax * half, cy + ay * half, 0.0)],
            closed=False, truncated_branch=False, excluded_edge_count=0, method="fallback_straight",
            confidence=0.5, notes=["No live graph/component data available; synthesized a straight "
                                    "line from family.length/orientation instead of recovering real geometry."],
        )

    def _bar_from_member(self, assembly: ReinforcementAssembly, family: Any, member: Any, layer, rep_path) -> PhysicalBar:
        # Path expansion (Phase 10C): translate the representative's
        # recovered path along the family's own perpendicular axis by this
        # member's offset -- the same signed projection axis already used
        # to compute offset_from_representative in
        # core/engineering/family.py, so a member at offset X ends up
        # exactly X away from the representative's path, preserving the
        # recovered shape (bends, arcs) rather than re-deriving a straight
        # line per member.
        angle = math.radians(getattr(family, "orientation", 0.0))
        ax, ay = math.cos(angle), math.sin(angle)
        px, py = -ay, ax
        offset = getattr(member, "offset_from_representative", 0.0)
        dx, dy = px * offset, py * offset

        raw_points = [(x + dx, y + dy, z) for x, y, z in rep_path.points]

        family_uuid = family.uuid
        member_uuid = member.uuid
        bar_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"physical-bar|{family_uuid}|{member_uuid}")

        annotated_diameter = getattr(family, "diameter", None)
        if annotated_diameter:
            diameter = float(annotated_diameter)
            diameter_source = "annotation"
            diameter_confidence = 1.0
        else:
            diameter = UNKNOWN_DIAMETER_VISUAL_MM
            diameter_source = "missing_visual_fallback"
            diameter_confidence = 0.0
        radius = diameter / 2.0

        centerline_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"bar-path|{family_uuid}|{member_uuid}")
        centerline = BarPath(
            uuid=centerline_uuid,
            family_uuid=family_uuid,
            member_uuid=member_uuid,
            points=raw_points,
            closed=rep_path.closed,
            recovery_method=rep_path.method,
            truncated_branch=rep_path.truncated_branch,
            excluded_edge_count=rep_path.excluded_edge_count,
            recovery_confidence=rep_path.confidence,
            recovery_notes=list(rep_path.notes),
        )
        adjusted_centerline, adjustment_notes = self.adjuster.apply_layer_and_cover(
            centerline,
            assembly.local_coordinate_system,
            layer.z_offset if layer else self._z_for_family(family),
            radius,
        )
        if rep_path.truncated_branch:
            adjustment_notes = adjustment_notes + [
                f"truncated_branch: {rep_path.excluded_edge_count} edge(s) excluded (see recovery_method)"
            ]

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
            diameter_source=diameter_source,
            diameter_confidence=diameter_confidence,
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
