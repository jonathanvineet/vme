"""Run the full DWG → 3D reconstruction pipeline.

Usage: python -m rebar3d.cli <dwg-or-dxf files...> [-o outdir]

Give it the (R) reinforcement drawings; each becomes one panel in the
combined viewer, with per-panel JSON + projection PNGs alongside.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .crosscheck import cross_check, format_report, parse_count_callouts
from .export import write_json, write_projections, write_viewer
from .extract import extract_bars
from .loader import dwg_to_dxf, load_entities
from .reconstruct import reconstruct_panel
from .schedule import compare_to_bars, extract_schedule, extract_schedule_dwg, find_schedule_pdf
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

        # Cross-check reconstructed bars against the drawing's own "N -T{d}"
        # count callouts — an independent sanity check against the source
        # text, separate from (and not fed into) the geometry-only
        # reconstruction above. SHORT entries are the trustworthy signal
        # (zero/too-few bars found near a labelled detail); OVER entries
        # are inflated whenever labels cluster close together and their
        # search radii overlap, see crosscheck.py.
        elev = views[0]
        callouts = parse_count_callouts(elev.ents)
        if callouts:
            bars2d = [b for b in extract_bars(elev.ents) if b.length >= 100.0]
            results = cross_check(callouts, bars2d)
            report = format_report(results)
            (args.out / f"{name}_crosscheck.txt").write_text(report + "\n")
            n_short = sum(1 for r in results if r.found < r.callout.count)
            print(f"  crosscheck: {len(callouts)} labelled details, {n_short} short "
                  f"(see {name}_crosscheck.txt)")

        # The sheet's own Summary Schedule is ground truth for weight —
        # independent of how well the geometry reconstruction above
        # manages to match it. Primary source: the DWG's own paper-space
        # layout (every panel carries its schedule there, even ones with
        # no PDF); fallback: a sibling (R) PDF.
        rows, src_name = extract_schedule_dwg(dxf), f"{name} DWG paper space"
        if rows is None:
            pdf = find_schedule_pdf(src)
            if pdf is not None:
                rows, src_name = extract_schedule(pdf), pdf.name
        if rows is not None:
            report = compare_to_bars(rows, panel.bars)
            (args.out / f"{name}_schedule.txt").write_text(report + "\n")
            official_tot = sum(r.weight_kg for r in rows)
            print(f"  official schedule ({src_name}): {official_tot:.1f}kg "
                  f"(see {name}_schedule.txt for reconstructed vs official per diameter)")

    write_viewer(panels, args.out / "viewer.html", title="Rebar 3D Reconstruction")
    print(f"viewer: {args.out / 'viewer.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
