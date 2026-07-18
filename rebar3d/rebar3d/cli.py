"""Run the full DWG → 3D reconstruction pipeline.

Usage: python -m rebar3d.cli <dwg-or-dxf files...> [-o outdir]

Give it the (R) reinforcement drawings; each becomes one panel in the
combined viewer, with per-panel JSON + projection PNGs alongside.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .export import write_json, write_projections, write_viewer
from .loader import dwg_to_dxf, load_entities
from .reconstruct import reconstruct_panel
from .views import cluster_views, elevation_candidates


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("drawings", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("out"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    panels = []
    for src in args.drawings:
        base_name = src.stem.replace("(R)", "").strip()
        geometry_only = "(M1)" in src.stem or "(M2)" in src.stem or "(M)" in src.stem
        dxf = dwg_to_dxf(src, args.out / "dxf") if src.suffix.lower() == ".dwg" else src
        ents = load_entities(dxf)
        views = cluster_views(ents)
        if not views:
            print(f"{base_name}: no drawable geometry found (schedule/table sheet?) — skipped")
            continue

        elevations = elevation_candidates(views)
        if len(elevations) <= 1:
            elevations = [views[0]]

        if len(elevations) > 1:
            print(f"  {base_name}: {len(elevations)} distinct member elevations found "
                  f"on this sheet — reconstructing each separately")
        elevation_ids = {id(v) for v in elevations}
        for i, elev in enumerate(elevations):
            name = f"{base_name}-{chr(ord('A') + i)}" if len(elevations) > 1 else base_name
            # scope this member's own view to itself plus every view that
            # isn't a sibling full elevation, so classify_sections() can't
            # mistake another member's elevation for a section cut of this one
            scoped = [elev] + [v for v in views if id(v) not in elevation_ids]
            panel = reconstruct_panel(name, scoped, geometry_only=geometry_only)

            panels.append(panel)
            write_json(panel, args.out / f"{name}.json")
            write_projections(panel, args.out / f"{name}_views.png")
            print(f"{name}: {panel.width:.0f}x{panel.height:.0f}x{panel.thickness:.0f} mm, "
                  f"{panel.stats['bars']} bars ({panel.stats['z_from_sections']} with section depth, "
                  f"{panel.stats['sections_found']} sections) z-planes={panel.stats['z_planes']}")

    write_viewer(panels, args.out / "viewer.html", title="Rebar 3D Reconstruction")
    print(f"viewer: {args.out / 'viewer.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
