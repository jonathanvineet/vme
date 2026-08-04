"""Run the full DWG → 3D reconstruction pipeline.

Usage: python -m rebar3d.cli <dwg-or-dxf files...> [-o outdir]

Give it the (R) reinforcement drawings; each becomes one panel in the
combined viewer, with per-panel JSON + projection PNGs alongside.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from .crosscheck import (
    cross_check, format_report, mark_report, parse_count_callouts,
    parse_letter_marks, text_callout_diameters,
)
from .export import write_json, write_projections, write_viewer
from .extract import extract_bars, wall_outline
from .loader import dwg_to_dxf, load_entities
from .reconstruct import (
    calibrate_edge_caps, calibrate_sleeve_wraps, calibrate_uniform_shape_lengths,
    cap_column_ties_to_schedule_need,
    cap_unproven_mesh_to_schedule_need,
    chain_bent_shape_fragments, chain_multi_leg_bent_shapes,
    chain_two_leg_bent_shapes, dowel_only_diameters, drop_unclaimed_tie_candidates,
    straight_mark_lengths,
    drop_undersized_mesh_fragments, drop_unscheduled_dowels, reconstruct_panel,
    synthesize_bent_shape_from_fragments, synthesize_from_detail_evidence,
)
from .schedule import (
    compare_to_bars, extract_schedule, extract_schedule_dwg, extract_itemized_bbs_dwg,
    find_schedule_pdf, parse_itemized_bbs,
)
from .reconstruct import Panel
from .sanity import sanity_check
from .sanity import format_report as format_sanity_report
from .schedule import ScheduleRow
from .views import cluster_views


def drop_unscheduled_phantoms(panel: Panel, rows: list[ScheduleRow], include_shape: bool = False) -> int:
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

    Deliberately excludes "shape" (bent, >2-point) bars: unlike a straight
    2-point mesh line, a shape survived `chain_bars` joining multiple real
    double-line segments end to end, which is much stronger evidence of a
    genuine bar than a straight rail-pairing artifact -- and a real bar can
    exist with no matching text callout at all (confirmed twice: SS-GF-01's
    T16 mesh has zero "T16" text anywhere in the DWG; PW-01's T12 bent bars
    have zero "T12" text either, yet its own official Summary Schedule
    confirms 8.43kg of real T12 steel). An earlier version of this filter
    included "shape" and wrongly deleted that real PW-01 T12 steel when
    running off the text-callout fallback (no official schedule existed
    for that panel at the time) -- restored once the actual schedule
    surfaced and proved it was real.

    `include_shape`: also drop "shape" bars at an absent diameter, but
    ONLY meant to be passed True when `rows` is a genuine Summary
    Schedule (a real material takeoff, not the `text_callout_diameters`
    fallback used when no schedule exists at all) -- that's precisely
    the gap the PW-01 regression above fell into, and it's scoped out
    here by leaving the caller's default False for the fallback path.
    With a real schedule, a diameter with zero official weight is
    definitive: PW-GF-08 root cause, a chained "shape" bar (0.09kg) at
    T6, a diameter completely absent from PW-GF-08(S).dwg's own Summary
    Schedule -- `chain_bars` occasionally joins two fragments of
    adjacent real diameters into a phantom bar whose paired-rail spacing
    snaps to a diameter that doesn't exist on the sheet at all, same
    class of artifact this function already removes for straight mesh,
    just surviving as a multi-point "shape" this time because it happened
    to chain across a bend.
    """
    official_dia = {r.diameter for r in rows}
    drop_kinds = ("v-mesh", "h-mesh", "diagonal", "shape") if include_shape \
        else ("v-mesh", "h-mesh", "diagonal")
    kept, dropped = [], 0
    for b in panel.bars:
        if b.kind in drop_kinds and b.z_source != "synthesized" \
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
    # groups sibling reinforcement sheets of one physical panel (e.g.
    # "PW-GF-05(R1)" + "PW-GF-05(R2)") by their shared base name, so their
    # weights can be summed before comparing to the ONE official schedule
    # they both share -- see the R1/R2 combination pass after this loop.
    combo_groups: dict[str, list[tuple[str, Panel]]] = {}
    combo_official: dict[str, tuple[list[ScheduleRow], str]] = {}
    combo_marks: dict[str, tuple[list, str]] = {}

    # Sharing one sibling sheet's itemized BBS with another (e.g. handing
    # R2's rich table to R1 too, since split reinforcement sheets share one
    # physical panel's steel takeoff) was tried and reverted: it does help
    # this panel's own T8, but it also hands marks whose real geometry only
    # exists on R2 to R1's synthesis/calibration passes, which then add real
    # weight for those marks ON TOP of R1's own already-excessive T16
    # geometry (a separate, still-open bug -- see `_z_lookup`'s docstring
    # discussion of PW-GF-27(R1)'s duplicated boundary-column depths) instead
    # of correcting it, making T16 worse, not better. Each sheet keeps its
    # own itemized resolution only; `combo_marks` below still lets the
    # COMBINE-time calibration re-run (`calibrate_edge_caps` /
    # `calibrate_uniform_shape_lengths`, which only ever tighten an existing
    # bar's length to a proven mark, never add new weight) use whichever
    # sibling's table is richest.
    for src in args.drawings:
        name = src.stem.replace("(R)", "").strip()
        dxf = dwg_to_dxf(src, args.out / "dxf") if src.suffix.lower() == ".dwg" else src
        ents = load_entities(dxf)
        views = cluster_views(ents)
        if not views:
            print(f"{name}: no elevation view found (schedule-only or non-rebar sheet), skipping")
            continue
        s_dwg = src.parent / f"{re.sub(r'\([^)]*\)\s*$', '', src.stem).strip()}(S).dwg"
        # Only trust a same-core-name "(S).dwg" when it's actually the same
        # revision/batch as `src` -- confirmed on PW-GF-09: an OLD single-
        # sheet "(R).dwg" (~2 months earlier) shares its base name with the
        # CURRENT batch's "(S).dwg", but they're different documents (its
        # own real geometry compared against the new schedule gave a
        # nonsense 553% on T12). Same-batch siblings are stamped within
        # minutes of each other; different revisions are months apart.
        s_dwg_ok = s_dwg.exists() and abs(s_dwg.stat().st_mtime - src.stat().st_mtime) < 7 * 86400
        s_dxf = dwg_to_dxf(s_dwg, args.out / "dxf") if s_dwg_ok else None

        # Itemized per-mark BBS, sourced early (before reconstruction) so
        # `reconstruct_panel` can exempt dowel-only diameters (see
        # `dowel_only_diameters`) from the purely-geometric column-tie
        # synthesizer -- moved up from its original post-reconstruction
        # spot below; the itemized-BBS sourcing logic itself is unchanged.
        itemized_candidates: list[tuple[str, list]] = []
        if s_dxf is not None:
            s_rows = extract_itemized_bbs_dwg(s_dxf)
            if s_rows is not None:
                itemized_candidates.append((s_dwg.name, s_rows))
        if not itemized_candidates:
            # This sheet's OWN paper space, tried before falling back to PDF
            # text extraction -- confirmed on PW-GF-27(R2): its own dxf
            # paper space carries the full 26-mark itemized table (A, A1,
            # A2, ..., J4), structured MTEXT read cleanly by
            # `extract_itemized_bbs_dwg`, but the code previously jumped
            # straight to `parse_itemized_bbs` on the sibling PDF, which
            # only ever recovered 1 of those 26 marks (just "I"). Losing
            # marks A-D (all the panel's T8) and G/J-family (T16) starved
            # every T8/T16 calibration and synthesis step below of real
            # schedule data, which is exactly what produced PW-GF-27's
            # T8-under / T10+T16+T20-over combined-sheet mismatch. The
            # summary-schedule `rows` block below already prefers this same
            # own-paper-space source over PDF for the identical reliability
            # reason; the itemized block just hadn't caught up.
            own_rows = extract_itemized_bbs_dwg(dxf)
            if own_rows is not None:
                itemized_candidates.append((name, own_rows))
        if not itemized_candidates:
            for pdf in find_schedule_pdf(src):
                if abs(pdf.stat().st_mtime - src.stat().st_mtime) >= 7 * 86400:
                    continue
                pdf_rows = parse_itemized_bbs(pdf)
                if pdf_rows is not None:
                    itemized_candidates.append((pdf.name, pdf_rows))
                    break
        tie_exempt_dias = (
            dowel_only_diameters(itemized_candidates[0][1]) if itemized_candidates else set()
        )
        straight_lengths = (
            straight_mark_lengths(itemized_candidates[0][1]) if itemized_candidates else {}
        )

        # Diameter-gap fill for the SUBTRACTIVE-only schedule checks below
        # (currently just `drop_undersized_mesh_fragments`): when this
        # sheet's own itemized table (above) never resolved a real mark
        # for some diameter at all -- not "resolved but sparse", literally
        # zero marks -- a sibling reinforcement sheet's own itemized table
        # (same "(R1)"/"(R2)"/... family, sharing one physical panel's
        # steel takeoff) is tried as a fallback source for THAT diameter
        # only. Root-caused on PW-GF-27(R1): its own itemized resolution
        # falls all the way through to a degraded 1-row PDF extraction
        # (only mark "I", T16) while its sibling (R2)'s own paper space
        # carries the real 25-row table -- so every diameter but T16 (T8,
        # T10, T20) has NO real schedule-length evidence on R1 at all,
        # letting `drop_undersized_mesh_fragments` skip real noise
        # (mis-paired short "mesh" fragments, confirmed on T20: 9 spurious
        # v-mesh/h-mesh fragments of 100-450mm alongside the 1 real
        # ~2.7m bar, none ever dropped for lack of a floor) clean through
        # to the final weight total.
        #
        # Deliberately NOT merged into `itemized_candidates`/`mark_rows`
        # itself: that was tried before (see the long comment on this
        # loop, below) and reverted -- handing a sibling's marks to the
        # ADDITIVE synthesis/calibration passes (chain_*, synthesize_*,
        # calibrate_*) let them add real weight for marks whose only
        # geometry lives on the sibling sheet, on top of this sheet's own
        # already-complete geometry for that diameter, inflating T16
        # further rather than fixing it. `drop_undersized_mesh_fragments`
        # is the one schedule-consuming pass that can only ever REMOVE a
        # bar (never invent one), so lending it extra floor evidence for a
        # diameter this sheet's own table is silent on carries none of
        # that risk -- and only ever fires for a diameter already totally
        # unrepresented in this sheet's own table, so a diameter with its
        # own (even sparse) real mark data is never touched by this.
        rm_self = re.search(r"\(R(\d+)\)$", src.stem)
        sibling_gap_rows: list = []
        if rm_self:
            base_stem = src.stem[:rm_self.start()]
            for sib in sorted(src.parent.glob(f"{base_stem}(R*).dwg")):
                if sib == src or not re.search(r"\(R\d+\)$", sib.stem):
                    continue
                if abs(sib.stat().st_mtime - src.stat().st_mtime) >= 7 * 86400:
                    continue
                sib_dxf = dwg_to_dxf(sib, args.out / "dxf")
                sib_rows = extract_itemized_bbs_dwg(sib_dxf)
                if sib_rows and len(sib_rows) > len(sibling_gap_rows):
                    sibling_gap_rows = sib_rows

        panel = reconstruct_panel(
            name, views, tie_exempt_dias=tie_exempt_dias, straight_lengths=straight_lengths)

        # The sheet's own Summary Schedule is ground truth for which
        # diameters actually appear in this panel at all — independent of
        # how well the geometry reconstruction manages to match it.
        # Priority: (1) a sibling "(S).dwg"'s own paper space -- the
        # dedicated schedule sheet by this drawing set's own naming
        # convention, most reliable when it exists; (2) this DWG's own
        # paper-space layout (every panel carries its schedule there when
        # it isn't split into a separate sheet); (3) sibling PDFs. Trying
        # this DWG's own paper space BEFORE the dedicated (S) sheet used
        # to risk exactly the bug `find_schedule_pdf` had (confirmed on
        # PW-GF-09: an unrelated, older same-named PDF's schedule doesn't
        # match this reconstruction's own panel at all) -- the (S) sheet
        # is unambiguous, so it goes first now.
        rows, src_name = None, None
        rows_is_dedicated_summary = False
        if s_dxf is not None:
            rows = extract_schedule_dwg(s_dxf)
            if rows is not None:
                src_name = f"{s_dwg.name} paper space"
                rows_is_dedicated_summary = True
        if rows is None:
            rows = extract_schedule_dwg(dxf)
            if rows is not None:
                src_name = f"{name} DWG paper space"
        if rows is None:
            for pdf in find_schedule_pdf(src):
                rows = extract_schedule(pdf)
                if rows is not None:
                    src_name = pdf.name
                    break
        if rows is not None:
            # `include_shape` is only safe with the dedicated "(S).dwg"
            # summary sheet as the source -- confirmed a genuine regression
            # on PW-GF-30(R2): its OWN paper-space/PDF schedule sources are
            # partial (425.4kg / 508.5kg, vs the panel's true combined
            # 508.5kg total), silently missing T16 entirely on that one
            # sheet even though real T16 steel legitimately sits there (its
            # sibling R1 carries the rest) -- treating that sheet-local gap
            # as "T16 doesn't exist on this panel" deleted 5.06kg of real
            # T16 "shape" bars. The "(S).dwg" summary sheet is the one
            # source this codebase already trusts as the authoritative full
            # takeoff (see the sourcing-priority comment above), so scoping
            # the new "shape" removal to it keeps the T6-phantom fix (a
            # genuinely absent diameter on PW-GF-08's own authoritative
            # summary) without risking a same-panel sheet-split gap
            # elsewhere.
            n_dropped = drop_unscheduled_phantoms(
                panel, rows, include_shape=rows_is_dedicated_summary)
            if n_dropped:
                print(f"  dropped {n_dropped} phantom bar(s) at diameters absent "
                      f"from the official schedule ({src_name})")
        else:
            # No Summary Schedule anywhere (no paper-space table, no sibling
            # PDF) -- fall back to every diameter the sheet's own text ever
            # mentions ("T8 @150 mm", "-(14) -T8", ...) as ground truth.
            # A diameter that never appears in any callout on the sheet but
            # shows up as a reconstructed v-mesh/h-mesh bar can only be a
            # generic-mesh rail mis-pairing artifact.
            text_dias = text_callout_diameters(ents)
            if text_dias:
                fake_rows = [ScheduleRow(d, 0.0, 0.0) for d in text_dias]
                n_dropped = drop_unscheduled_phantoms(panel, fake_rows)
                if n_dropped:
                    print(f"  dropped {n_dropped} phantom bar(s) at diameters absent "
                          f"from the sheet's own text callouts (no official schedule found)")

        # Itemized per-mark BBS ("Rebar schedule for X"). Prefer a sibling
        # "(S).dwg"'s own paper space (`extract_itemized_bbs_dwg`) over PDF
        # text extraction when one exists -- structured MTEXT cells read
        # more reliably than pypdf's cell-per-line text dump, and it's the
        # only source at all for panels with no PDF. Falls back to the PDF
        # candidates otherwise. Lets us complete sleeve-wrap brackets that
        # geometry-only pairing only ever captures half of -- anchored at
        # the panel's own already-detected real sleeve positions, not
        # guessed. Symmetric-U rows only (segments [0, leg, gap, leg, 0]):
        # the standard "wrap a duct" bracket shape confirmed against the
        # R-sheet's own "U-BAR DETAIL" callout.
        mark_groups = parse_letter_marks(ents, views)
        (mx0, my0, _mx1, _my1), _ = wall_outline(views[0].ents)

        # `itemized_candidates` (PDF text extraction is a fallback for
        # panels with no reliable DWG-sourced itemized table, not a second
        # independent source to run alongside it; also guarded by the same
        # `s_dwg_ok`-style staleness check -- see comment where it's
        # sourced, above, near `reconstruct_panel`) was already computed
        # earlier in this loop, before `reconstruct_panel` ran, so
        # `tie_exempt_dias` could be derived from it.
        for src_label, mark_rows in itemized_candidates:
            # Only marks with direct visual confirmation (the R-sheet's own
            # "U-BAR DETAIL" callout explicitly names D4/D5 wrapping the
            # sleeve) -- the shape alone ("symmetric U", segments
            # [0, leg, gap, leg, 0]) is NOT a safe filter on its own: H/H1
            # share the exact same shape topology but are a completely
            # unrelated detail, and including them by shape match alone
            # blew T12 out to 202% of schedule in testing.
            sleeve_marks = [
                (m.diameter, m.segments[1], m.segments[2], m.qty)
                for m in mark_rows if m.mark in ("D4", "D5")
            ]
            if sleeve_marks:
                n_cal = calibrate_sleeve_wraps(panel, sleeve_marks)
                if n_cal:
                    print(f"  calibrated {n_cal} sleeve-wrap bar(s) from {src_label} "
                          f"(anchored at real detected sleeve positions)")

            # "Hook"/edge-cap family length correction: position/count
            # already come from real icon geometry (see
            # `_synthesize_edge_caps`); when that count matches one
            # schedule mark's quantity exactly, trust that mark's own
            # stated length over the unreliable arc-measurement fallback.
            edge_cap_marks = [(m.diameter, m.qty, m.length_mm) for m in mark_rows]
            n_len_fixed = calibrate_edge_caps(panel, edge_cap_marks)
            if n_len_fixed:
                print(f"  corrected length of {n_len_fixed} edge-cap bar(s) from "
                      f"{src_label} (count already matched a schedule mark exactly)")

            # Same idea, generalized beyond the "hook" kind: a v-mesh/h-
            # mesh/shape family whose count exactly matches one mark AND
            # whose members are all suspiciously uniform in length is the
            # same "one segment of a repeated bent shape measured as the
            # whole bar" bug, just landing on an ordinary mesh kind this
            # time (confirmed on PW-GF-09's mark H).
            n_uniform_fixed = calibrate_uniform_shape_lengths(panel, mark_rows)
            if n_uniform_fixed:
                print(f"  corrected length of {n_uniform_fixed} uniform-length bar(s) from "
                      f"{src_label} (count and uniformity matched a schedule mark exactly)")

            # A diameter with real schedule marks but none of them a
            # dowel-bend shape ("M_17A") has no business owning any
            # face-dowel/link bar -- drops circles that got wrongly
            # promoted into dowels by a geometry bug (see the long
            # unresolved-bug comment in reconstruct_panel's circle-
            # promotion loop).
            n_dowel_dropped = drop_unscheduled_dowels(panel, mark_rows)
            if n_dowel_dropped:
                print(f"  dropped {n_dowel_dropped} dowel-kind bar(s) at diameters with "
                      f"no dowel-shaped mark in {src_label}")

            n_stitched, n_frags_used = chain_bent_shape_fragments(panel, mark_rows)
            if n_stitched:
                print(f"  chained {n_frags_used} disjoint mesh fragment(s) into {n_stitched} "
                      f"complete bent bar(s) from {src_label} (stitched path length matched "
                      f"a real bent-shape mark within 15%)")

            n_multi_stitched, n_multi_frags = chain_multi_leg_bent_shapes(panel, mark_rows)
            if n_multi_stitched:
                print(f"  chained {n_multi_frags} disjoint mesh fragment(s) into {n_multi_stitched} "
                      f"complete bent bar(s) from {src_label} (each leg's own length matched "
                      f"the mark's own segment sequence, not just the finished total)")

            n_two_leg, two_leg_kg = chain_two_leg_bent_shapes(panel, mark_rows)
            if n_two_leg:
                print(f"  synthesized {n_two_leg} bent-shape bar(s) ({two_leg_kg:.1f}kg) from "
                      f"{src_label} (two real fragments each individually matched one of the "
                      f"mark's own two declared leg lengths, even though their endpoints don't "
                      f"touch)")

            n_bent_added, bent_kg = synthesize_bent_shape_from_fragments(
                panel, mark_rows, mark_groups, mx0, my0)
            if n_bent_added:
                print(f"  synthesized {n_bent_added} bent-shape bar(s) ({bent_kg:.1f}kg) from "
                      f"{src_label} marks with real fragment evidence near their own label "
                      f"(count trusted from the schedule, not re-measured off broken geometry)")

            own_dias = {m.diameter for m in mark_rows}
            gap_fill = [m for m in sibling_gap_rows if m.diameter not in own_dias]
            n_frag_dropped, frag_kg = drop_undersized_mesh_fragments(
                panel, mark_rows + gap_fill)
            if n_frag_dropped:
                gap_note = (
                    f" (plus diameter(s) {sorted({m.diameter for m in gap_fill})} floored "
                    f"from a sibling sheet, absent from {src_label} itself)" if gap_fill else ""
                )
                print(f"  dropped {n_frag_dropped} undersized mesh fragment(s) ({frag_kg:.1f}kg) "
                      f"shorter than any real mark at that diameter in {src_label}{gap_note}")

            n_tie_noise, tie_noise_kg = drop_unclaimed_tie_candidates(
                panel, mark_rows, panel.width, panel.height, panel.thickness)
            if n_tie_noise:
                print(f"  dropped {n_tie_noise} unclaimed full-span mesh line(s) "
                      f"({tie_noise_kg:.1f}kg) at a dowel-only diameter in {src_label} "
                      f"(tie-candidate-shaped but matches no real mark, and no longer "
                      f"absorbed into a fabricated tie now that this diameter is exempt)")

            # Fill true architecture-gap marks: real S-RBAR geometry sits
            # next to the label but only in a local detail view the
            # elevation/section pipeline never scans (see
            # `synthesize_from_detail_evidence`).
            n_detail_added, detail_kg = synthesize_from_detail_evidence(
                panel, views, mark_rows, mark_groups, mx0, my0)
            if n_detail_added:
                print(f"  synthesized {n_detail_added} bar(s) ({detail_kg:.1f}kg) from "
                      f"{src_label} marks whose only real geometry sits in a local "
                      f"detail view (not the elevation or a full section cut)")


            n_tie_dropped, tie_kg = cap_column_ties_to_schedule_need(panel, mark_rows)
            if n_tie_dropped:
                print(f"  trimmed {n_tie_dropped} synthesized column-tie bar(s) ({tie_kg:.1f}kg) "
                      f"exceeding {src_label}'s own remaining weight budget at that diameter")

            n_mesh_dropped, mesh_kg = cap_unproven_mesh_to_schedule_need(panel, mark_rows)
            if n_mesh_dropped:
                print(f"  trimmed {n_mesh_dropped} non-section-backed mesh bar(s) ({mesh_kg:.1f}kg) "
                      f"exceeding {src_label}'s own remaining weight budget at that diameter")
            break

        panels.append(panel)
        write_json(panel, args.out / f"{name}.json")
        write_projections(panel, args.out / f"{name}_views.png")
        print(f"{name}: {panel.width:.0f}x{panel.height:.0f}x{panel.thickness:.0f} mm, "
              f"{panel.stats['bars']} bars ({panel.stats['z_from_sections']} with section depth, "
              f"{panel.stats['sections_found']} sections) z-planes={panel.stats['z_planes']}")

        # Automated sanity checks -- deterministic, no LLM: concrete rules
        # (z-bounds, steel-to-concrete ratio, outlier bar lengths, degenerate
        # dims) that catch an implausible reconstruction automatically
        # instead of waiting for someone to spot it in the viewer. A flag
        # here is a lead to go trace, not a verdict.
        #
        # Skipped on mould sheets ((M)/(M1)/(M2)): they carry little or no
        # rebar by design (dims/insert-schedule sheets, real reinforcement
        # lives on the (R) sheet), so a low steel-to-concrete ratio there is
        # expected, not suspicious -- the check would be pure noise.
        is_mould = any(s in src.stem for s in ("(M)", "(M1)", "(M2)"))
        findings = [] if is_mould else sanity_check(panel)
        (args.out / f"{name}_sanity.txt").write_text(format_sanity_report(findings) + "\n")
        errors = [f for f in findings if f.severity == "error"]
        warns = [f for f in findings if f.severity == "warn"]
        if findings:
            print(f"  sanity: {len(errors)} error(s), {len(warns)} warning(s) "
                  f"(see {name}_sanity.txt)")
            for f in findings:
                print(f"    [{f.severity.upper()}] {f.message}")

        # Cross-check reconstructed bars against the drawing's own "N -T{d}"
        # count callouts — an independent sanity check against the source
        # text, separate from (and not fed into) the geometry-only
        # reconstruction above. SHORT entries are the trustworthy signal
        # (zero/too-few bars found near a labelled detail); OVER entries
        # are inflated whenever labels cluster close together and their
        # search radii overlap, see crosscheck.py.
        #
        # Drawing-wide, not elevation-only: most count callouts for corbel
        # main bars, perimeter bars, and edge-beam rail ambiguities sit in
        # a section/detail view, not the elevation (confirmed on PW-45/
        # SS-GF-01: only 1 of 12 such callouts fell inside the elevation's
        # own bbox) — checking only views[0] silently skipped almost every
        # one of them. Each view is checked against its own local geometry
        # (never cross-view) since a detail view's coordinates have no
        # reliable relationship to the elevation's.
        callouts = []
        results = []
        for v in views:
            v_callouts = parse_count_callouts(v.ents)
            if not v_callouts:
                continue
            v_bars2d = [b for b in extract_bars(v.ents) if b.length >= 100.0]
            callouts += v_callouts
            results += cross_check(v_callouts, v_bars2d)
        if callouts:
            report = format_report(results)
            (args.out / f"{name}_crosscheck.txt").write_text(report + "\n")
            n_short = sum(1 for r in results if r.found < r.callout.count)
            print(f"  crosscheck: {len(callouts)} labelled details, {n_short} short "
                  f"(see {name}_crosscheck.txt)")

        # Schedule-mark-letter reconciliation: pairs every letter label
        # ("B", "D", "G", ...) with its real, deduped total count (see
        # `parse_letter_marks`) and checks it against reconstructed
        # geometry -- a sharper, mark-scoped view of the same gaps the
        # per-callout crosscheck above already flags, useful for tracing a
        # specific official schedule row back to its real DWG evidence.
        if mark_groups:
            report = mark_report(mark_groups, panel.bars, mx0, my0)
            (args.out / f"{name}_marks.txt").write_text(report + "\n")
            n_mark_short = sum(1 for line in report.splitlines() if "SHORT" in line)
            print(f"  marks: {len(mark_groups)} schedule-letter mark(s) identified, "
                  f"{n_mark_short} short (see {name}_marks.txt)")

        if rows is not None:
            report = compare_to_bars(rows, panel.bars)
            (args.out / f"{name}_schedule.txt").write_text(report + "\n")
            official_tot = sum(r.weight_kg for r in rows)
            print(f"  official schedule ({src_name}): {official_tot:.1f}kg "
                  f"(see {name}_schedule.txt for reconstructed vs official per diameter)")

        # Only sheets literally split into numbered reinforcement parts
        # ("(R1)", "(R2)", ...) get grouped -- NOT plain "(R)" (a single,
        # complete sheet needs no combining) and not "(M...)"/"(S)" (a
        # different sheet type entirely, never sharing the same steel
        # takeoff as the reinforcement sheets).
        rm = re.search(r"\(R(\d+)\)$", src.stem)
        if rm:
            base = src.stem[:rm.start()]
            combo_groups.setdefault(base, []).append((name, panel))
            if rows is not None and base not in combo_official:
                combo_official[base] = (rows, src_name)
            if itemized_candidates:
                # Prefer whichever sibling sheet's itemized table has the
                # most rows, not just whichever sheet happened to be
                # processed first -- confirmed on PW-GF-27: R1 (processed
                # first) only ever resolves a 1-row PDF-fallback table while
                # R2's own paper space carries the real 26-row table, and
                # first-come-first-served locked the combine-time
                # calibration re-run (`calibrate_edge_caps` /
                # `calibrate_uniform_shape_lengths` below) onto the near-
                # empty one.
                cand = itemized_candidates[0]
                if base not in combo_marks or len(cand[1]) > len(combo_marks[base][1]):
                    combo_marks[base] = cand

    # R1+R2(+...) combination: sum every sibling sheet's reconstructed
    # weight per diameter and compare against their ONE shared official
    # schedule -- confirmed necessary on the PW-GF-05..30 batch, where
    # each split sheet covers a physically different wing/leg of one
    # panel (different width/thickness even) and was never going to
    # individually reach 100% of the combined total; reporting each
    # sheet's own ratio against the FULL schedule was actively
    # misleading (R2 sheets routinely read 2-20%, looking like a near-
    # total loss, when the real combined total is often 70-90%).
    for base, members in combo_groups.items():
        if len(members) < 2 or base not in combo_official:
            continue
        rows, src_name = combo_official[base]
        all_bars = [b for _n, p in members for b in p.bars]
        member_names = ", ".join(n for n, _p in members)

        # A family split across sibling sheets (e.g. 2 bars of one mark
        # drawn on R1, 2 more of the SAME mark on R2) never reaches its
        # real full count within either sheet alone, so the per-sheet
        # calibration pass above never fires for it -- confirmed on
        # PW-GF-09's mark K (4x T16): exactly 2 near-identical-length bars
        # sit on each of R1 and R2, invisible to a single-sheet count
        # check but an exact match once combined. Re-running the same,
        # already-proven-safe calibrations here on the COMBINED bar list
        # mutates the real `Bar3D` objects in place (shared by reference
        # with each member panel's own `.bars`), so the fix lands in both
        # this combined report AND each panel's own JSON/viewer -- safe to
        # re-run even for marks already fixed per-sheet, since both
        # functions skip a group that's already close to the target
        # length.
        if base in combo_marks:
            _label, combo_mark_rows = combo_marks[base]
            fake_panel = SimpleNamespace(bars=all_bars)
            n1 = calibrate_edge_caps(
                fake_panel, [(m.diameter, m.qty, m.length_mm) for m in combo_mark_rows])
            n2 = calibrate_uniform_shape_lengths(fake_panel, combo_mark_rows)
            if n1 or n2:
                print(f"{base}: corrected length of {n1 + n2} bar(s) split across "
                      f"{member_names} (count only matched once combined)")

            # Each sibling sheet's own per-sheet budget cap
            # (`cap_column_ties_to_schedule_need` / `cap_unproven_mesh_
            # to_schedule_need`) only ever sees ITS OWN bars against the
            # full shared official total -- when a sheet has no itemized
            # table of its own (falls back to the one shared official
            # schedule, e.g. PW-GF-30(R1) borrowing PW-GF-30(R2).pdf) it
            # has no way to know a sibling sheet will independently spend
            # more of that same budget, so it under-trims. Root-caused on
            # PW-GF-30: R1's cap correctly capped itself to <= the full
            # T8 budget (158.1kg) in isolation, but R2 then added its own
            # ~22.9kg of trusted, uncapped T8 bars on top, landing the
            # true combined total at 115% (181.3kg). Re-running both caps
            # here on the COMBINED bar list against the same combined
            # mark rows already used for the calibration re-run above
            # closes that gap the same safe way: each cap only trims
            # v-mesh/h-mesh (or synthesized tie) bars whose own diameter
            # total, across BOTH sheets together, exceeds what the real
            # schedule calls for -- a panel that genuinely needs every
            # one of those bars to reach its official weight is
            # untouched, exactly as when run per-sheet.
            n3, tie_kg = cap_column_ties_to_schedule_need(fake_panel, combo_mark_rows)
            n4, mesh_kg = cap_unproven_mesh_to_schedule_need(fake_panel, combo_mark_rows)
            if n3 or n4:
                print(f"{base}: trimmed {n3 + n4} bar(s) ({tie_kg + mesh_kg:.1f}kg) "
                      f"exceeding the combined schedule's own remaining weight budget "
                      f"(only visible once {member_names} are summed together)")

            if n1 or n2 or n3 or n4:
                all_bars = fake_panel.bars
                kept_ids = {id(b) for b in all_bars}
                for _n, p in members:
                    p.bars = [b for b in p.bars if id(b) in kept_ids]
                    write_json(p, args.out / f"{p.name}.json")

        report = compare_to_bars(rows, all_bars)
        header = f"Combined: {member_names}\nOfficial: {src_name}\n\n"
        (args.out / f"{base}_combined_schedule.txt").write_text(header + report + "\n")
        official_tot = sum(r.weight_kg for r in rows)
        recon_tot = sum(b.diameter ** 2 / 162.0 *
                        sum(((b.points[i + 1][0] - b.points[i][0]) ** 2 +
                             (b.points[i + 1][1] - b.points[i][1]) ** 2 +
                             (b.points[i + 1][2] - b.points[i][2]) ** 2) ** 0.5
                            for i in range(len(b.points) - 1)) / 1000.0
                        for b in all_bars)
        print(f"{base}: combined {member_names} = {recon_tot:.1f}kg of official "
              f"{official_tot:.1f}kg ({100 * recon_tot / official_tot:.0f}%), "
              f"see {base}_combined_schedule.txt")

    write_viewer(panels, args.out / "viewer.html", title="Rebar 3D Reconstruction")
    print(f"viewer: {args.out / 'viewer.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
