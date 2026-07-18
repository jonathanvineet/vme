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
from .reconstruct import Panel
from .schedule import ScheduleRow
from .views import cluster_views


def drop_unscheduled_phantoms(panel: Panel, rows: list[ScheduleRow]) -> int:
    """Drop generic-mesh bars at a diameter the panel's own official
    schedule never lists at all.

    The Summary Schedule is a full material takeoff of every diameter
    actually drawn on the sheet; a v-mesh/h-mesh/diagonal bar (plain
    double-line pairing off S-RBAR, not a cast-in item with its own
    separate schedule and not a text-callout synthesis already anchored
    to a diameter the drawing states) at a diameter absent from that
    takeoff is drafting noise -- e.g. two lines an unrelated distance
    apart happening to fall in [MIN_DIA, MAX_DIA] at a bar-boundary
    transition -- not real steel. Confirmed on PW-GF-02: phantom T25/T32
    v-mesh/h-mesh bars sitting exactly between two real, correctly-paired
    bars of different diameters (T12/T8, T20/T8), i.e. one rail of each
    real bar cross-paired with a rail of its neighbour.
    """
    official_dia = {r.diameter for r in rows}
    kept, dropped = [], 0
    for b in panel.bars:
        if b.kind in ("v-mesh", "h-mesh", "diagonal") and b.z_source != "synthesized" \
                and b.diameter not in official_dia:
            dropped += 1
            continue
        kept.append(b)
    panel.bars = kept
    if dropped:
        panel.stats["bars"] = len(kept)
    return dropped


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

        # The sheet's own Summary Schedule is ground truth for which
        # diameters actually appear in this panel at all — independent of
        # how well the geometry reconstruction manages to match it.
        # Primary source: the DWG's own paper-space layout (every panel
        # carries its schedule there, even ones with no PDF); fallback: a
        # sibling (R) PDF.
        rows, src_name = extract_schedule_dwg(dxf), f"{name} DWG paper space"
        if rows is None:
            pdf = find_schedule_pdf(src)
            if pdf is not None:
                rows, src_name = extract_schedule(pdf), pdf.name
        if rows is not None:
            n_dropped = drop_unscheduled_phantoms(panel, rows)
            if n_dropped:
                print(f"  dropped {n_dropped} phantom bar(s) at diameters absent "
                      f"from the official schedule ({src_name})")

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
