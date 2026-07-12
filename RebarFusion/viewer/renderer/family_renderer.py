from __future__ import annotations

import math

import numpy as np
import pyvista as pv

from viewer.renderer.base_renderer import BaseRenderer
from viewer.scene import SceneManager


class FamilyRenderer(BaseRenderer):
    """
    Phase 11.1: draws each family member using its actual PhysicalBar.path
    (the Phase 10.1 recovered geometry -- bends, arcs, branch shape all
    preserved), not a synthesized straight line from family.length/
    orientation. Before this fix, this renderer independently re-derived a
    straight-line approximation, which would have visibly contradicted
    BarRenderer/MeshRenderer's real recovered geometry the moment the
    viewer's pipeline staleness (see docs/audits/phase11/11.0_viewer_audit.md)
    was fixed -- both views now read from the same PhysicalBar objects, so
    they can't disagree.
    """
    LAYER_NAME = SceneManager.LAYER_FAMILIES

    def build(self):
        families = getattr(self.scene, "engineering_families", None)
        if not families:
            return

        bars_by_member = {
            (bar.family_uuid, bar.member_uuid): bar
            for bar in (getattr(self.scene, "physical_bars", None) or [])
        }

        colors = [
            (0.30, 0.64, 1.00),
            (0.39, 0.83, 0.43),
            (1.00, 0.82, 0.40),
            (0.75, 0.52, 0.99),
            (0.95, 0.55, 0.42),
        ]

        for idx, family in enumerate(families):
            color = self._qa_color(family) if self.scene.show_family_qa else colors[idx % len(colors)]
            selected = self.scene.selected_family_uuid == family.uuid
            line_width = 5.0 if selected else 3.0
            z = 2.0 + idx * 0.02

            members = []
            if self.scene.show_family_expanded:
                members = list(family.members)
            elif self.scene.show_family_representative and family.members:
                members = [family.members[0]]
            if self.scene.show_family_representative and self.scene.show_family_expanded and family.members:
                rep = family.members[0]
                rep_bar = bars_by_member.get((family.uuid, rep.uuid))
                rep_mesh = self._member_mesh(rep_bar, rep, z + 0.06)
                if rep_mesh is not None:
                    actor = self.plotter.add_mesh(
                        rep_mesh,
                        color=(1.0, 1.0, 1.0),
                        line_width=line_width + 1.0,
                        opacity=0.9,
                        name=f"family_rep_{str(family.uuid)[:8]}",
                        pickable=True,
                    )
                    self._add_actor(actor)

            for member in members:
                bar = bars_by_member.get((family.uuid, member.uuid))
                mesh = self._member_mesh(bar, member, z)
                if mesh is None:
                    continue
                actor = self.plotter.add_mesh(
                    mesh,
                    color=color,
                    line_width=line_width,
                    opacity=0.95,
                    name=f"family_{str(family.uuid)[:8]}_{str(member.component_uuid)[:8]}",
                    pickable=True,
                )
                self._add_actor(actor)

            if not self.scene.show_family_missing:
                continue
            for missing_offset in family.missing_member_offsets:
                # No PhysicalBar exists for an inferred-but-undetected
                # member -- there is no real geometry to draw, so this one
                # legitimately stays a synthesized placeholder (dashed, to
                # visually distinguish it from real recovered bars above).
                mesh = self._missing_member_mesh(family, missing_offset, z + 0.04)
                if mesh:
                    actor = self.plotter.add_mesh(
                        mesh,
                        color=(1.0, 0.20, 0.20),
                        line_width=2.5,
                        opacity=0.9,
                        name=f"family_missing_{str(family.uuid)[:8]}_{missing_offset:.0f}",
                    )
                    self._add_actor(actor)

    def _member_mesh(self, bar, member, z: float):
        """Uses bar.path (Phase 10.1 recovered geometry) when a PhysicalBar
        exists for this member. Falls back to a straight line from the
        member's own length/orientation only if no bar was built for it
        (e.g. viewer running against a Phase 9-only bundle with no
        reconstruction stage) -- never silently prefers synthesis when real
        geometry is available."""
        if bar is not None and bar.path and len(bar.path) >= 2:
            points = np.array([(x, y, z) for x, y, _ in bar.path])
            mesh = pv.PolyData()
            mesh.points = points
            lines = []
            for i in range(len(points) - 1):
                lines.extend([2, i, i + 1])
            mesh.lines = np.array(lines)
            return mesh

        cx, cy = member.centroid
        angle = math.radians(member.orientation)
        ax, ay = math.cos(angle), math.sin(angle)
        half = member.length / 2.0
        points = np.array([
            [cx - ax * half, cy - ay * half, z],
            [cx + ax * half, cy + ay * half, z],
        ])
        mesh = pv.PolyData()
        mesh.points = points
        mesh.lines = np.array([2, 0, 1])
        return mesh

    def _missing_member_mesh(self, family, missing_offset: float, z: float):
        if not family.members:
            return None

        rep = family.members[0]
        angle = math.radians(family.orientation)
        ax, ay = math.cos(angle), math.sin(angle)
        px, py = -ay, ax
        cx = rep.centroid[0] + px * missing_offset
        cy = rep.centroid[1] + py * missing_offset
        half = family.length / 2.0
        p1 = (cx - ax * half, cy - ay * half)
        p2 = (cx + ax * half, cy + ay * half)

        dash = max(family.length / 28.0, 80.0)
        gap = dash * 0.65
        total = family.length
        segments = []
        t = 0.0
        while t < total:
            end = min(t + dash, total)
            a = t / total
            b = end / total
            segments.append([
                p1[0] + (p2[0] - p1[0]) * a,
                p1[1] + (p2[1] - p1[1]) * a,
                z,
            ])
            segments.append([
                p1[0] + (p2[0] - p1[0]) * b,
                p1[1] + (p2[1] - p1[1]) * b,
                z,
            ])
            t += dash + gap

        if not segments:
            return None
        lines = []
        for idx in range(0, len(segments), 2):
            lines.extend([2, idx, idx + 1])

        mesh = pv.PolyData()
        mesh.points = np.array(segments)
        mesh.lines = np.array(lines)
        return mesh

    @staticmethod
    def _qa_color(family):
        if family.confidence >= 0.85 and not (family.qa and family.qa.warnings):
            return (0.25, 0.85, 0.35)
        if family.confidence >= 0.5:
            return (1.0, 0.82, 0.25)
        return (1.0, 0.25, 0.25)
