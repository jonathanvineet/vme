from __future__ import annotations

from typing import List, Tuple

from core.reconstruction.models import BarPath, CoordinateFrame


class ReinforcementAdjuster:
    def apply_layer_and_cover(
        self,
        centerline: BarPath,
        frame: CoordinateFrame,
        layer_z_offset: float,
        radius: float,
    ) -> Tuple[BarPath, List[str]]:
        target_z = frame.cover + layer_z_offset + radius
        adjusted_points = [(x, y, target_z) for x, y, _ in centerline.points]
        notes = [f"cover={frame.cover:.1f}", f"layer_z_offset={layer_z_offset:.1f}"]
        return (
            BarPath(
                uuid=centerline.uuid,
                family_uuid=centerline.family_uuid,
                member_uuid=centerline.member_uuid,
                points=adjusted_points,
                bends=centerline.bends,
                hooks=centerline.hooks,
                closed=centerline.closed,
            ),
            notes,
        )
