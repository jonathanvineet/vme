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
from .views import cluster_views


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("drawings", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("out"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    panels = []
    for src in args.drawings:
        name = src.stem.replace("(R)", "").strip()
        dxf = dwg_to_dxf(src, args.out / "dxf") if src.suffix.lower() == ".dwg" else src
        ents = load_entities(dxf)
        views = cluster_views(ents)
        panel = reconstruct_panel(name, views)
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
