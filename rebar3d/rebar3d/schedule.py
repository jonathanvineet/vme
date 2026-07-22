"""Extract and compare against the drawing's own printed "Summary Schedule".

The (R) sheet's Summary Schedule table (per-diameter total bar length +
weight) is ground truth: it's what the drawing itself declares, produced
from the live Revit model, independent of how well this pipeline's
geometry-only reconstruction manages to re-derive the same numbers. 3D
reconstruction accuracy is a long tail of individually distinct geometric
edge cases (confirmed repeatedly: fabricated diameters, depth mismatches,
bars invisible to double-line pairing, bars only in a detail view) that
won't all close quickly. Surfacing the schedule directly, alongside
whatever the reconstruction currently produces, gives an always-accurate
weight number without waiting on that reconstruction work to finish.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScheduleRow:
    diameter: int
    length_mm: float
    weight_kg: float


def extract_schedule(pdf_path: Path) -> list[ScheduleRow] | None:
    """Parse the Summary Schedule table off the first page of an (R) PDF.

    Returns None if the PDF has no such table (not every panel's sheet
    carries one, e.g. mould-only sheets).
    """
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()
    m = re.search(r"summary\s*schedule", text, re.IGNORECASE)
    if m is None:
        return None
    idx = m.start()
    rows = [
        ScheduleRow(int(m.group(1)), float(m.group(2)), float(m.group(3)))
        for m in re.finditer(r"(\d+)\s*mm\s+([\d.]+)\s*mm\s+([\d.]+)\s*kg", text[idx:])
    ]
    return rows or None


def extract_schedule_dwg(dxf_path: Path) -> list[ScheduleRow] | None:
    """Read the Summary Schedule directly out of the DWG's paper space.

    The schedule table isn't in modelspace (checking only modelspace led
    this project to wrongly conclude the DWG carries no schedule text at
    all) — it's MTEXT in the print layout (paper space), cell by cell.
    Reconstructing the table = grouping "N mm"/"N kg" cells into rows by
    Y coordinate. Verified to reproduce the printed PDF table exactly on
    all four available panels — including PW-GF-45, which has no PDF at
    all, making this the only source of official totals for such panels.
    """
    import ezdxf

    try:
        doc = ezdxf.readfile(str(dxf_path))
    except IOError:
        return None
    for lname in doc.layout_names():
        if lname.lower() == "model":
            continue
        items = []
        has_title = False
        for e in doc.layout(lname):
            if e.dxftype() != "MTEXT":
                continue
            s = e.plain_text().strip()
            if s == "Summary Schedule":
                has_title = True
            items.append((s, e.dxf.insert.x, e.dxf.insert.y))
        if not has_title:
            continue
        cells = [(s, x, y) for s, x, y in items
                 if re.fullmatch(r"[\d.]+ (?:mm|kg)", s)]
        # group cells into table rows by Y, then order columns by X
        rows_by_y: list[list] = []
        for s, x, y in sorted(cells, key=lambda c: -c[2]):
            for r in rows_by_y:
                if abs(r[0] - y) < 3:
                    r[1].append((x, s))
                    break
            else:
                rows_by_y.append([y, [(x, s)]])
        out = []
        for _, cl in rows_by_y:
            cl.sort()
            vals = [s for _, s in cl]
            # a data row is: "<dia> mm", "<length> mm", "<weight> kg";
            # the totals row has only two cells (length, weight) — skip it
            if len(vals) == 3 and vals[0].endswith(" mm") and vals[2].endswith(" kg"):
                dia = float(vals[0][:-3])
                if dia <= 50:  # sanity: a diameter, not a length
                    out.append(ScheduleRow(int(dia), float(vals[1][:-3]), float(vals[2][:-3])))
        if out:
            return out
    return None


@dataclass
class MarkRow:
    """One row of a "Rebar schedule for X" itemized table (cell-per-line
    layout, e.g. DRAWINGS/PW-01(S).pdf) -- distinct from ScheduleRow, which
    is the coarser per-diameter Summary Schedule."""
    mark: str
    diameter: int
    shape: str
    segments: list[float]  # A,B,C,... in mm, zeros kept (positional) -- 5 or
                           # more columns depending on the sheet (confirmed
                           # PW-GF-05 uses A/B/C/D/E/G, 6 columns, not PW-01's
                           # fixed 5 -- don't assume a fixed count)
    length_mm: float       # one bar
    total_length_mm: float
    qty: int
    weight_kg: float
    location: str = ""     # e.g. "WALL - 30mm" / "CORBEL - 25mm" cover note,
                           # when the sheet prints one (DWG paper-space table
                           # only; not available in the PDF text extraction)
    part: str = ""         # which sub-schedule this came from, e.g. "A" for
                           # "Rebar schedule for PW-GF-05(A)" -- a multi-wing
                           # panel can have several (A)/(B)/(C) sub-tables


_MARK_ROW_RE = re.compile(
    r"^(\S+)\n(\d+) mm\n([^\n]+)\n(\d+) mm\n(\d+) mm\n(\d+) mm\n(\d+) mm\n(\d+) mm\n"
    r"(\d+) mm\n(\d+) mm\n(\d+)\n([\d.]+) kg",
    re.MULTILINE,
)


def parse_itemized_bbs(pdf_path: Path) -> list[MarkRow] | None:
    """Parse a "Rebar schedule for X" itemized table (Schedule Mark / Bar
    Diameter / Shape / A / B / C / D / E / Bar Length / Total Bar Length /
    Quantity / weight), one value per line -- the cell layout pypdf yields
    for this drawing set's "(S)" schedule sheets, distinct from both the
    Summary Schedule (extract_schedule) and the separate itemized-BBS PDFs
    parse_bbs_pdf handles (which use one-line-per-row instead).
    """
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    text = "\n".join(p.extract_text() for p in reader.pages)
    idx = text.find("Rebar schedule for")
    if idx < 0:
        return None
    rows = []
    for m in _MARK_ROW_RE.finditer(text[idx:]):
        mark, dia, shape, a, b, c, d, e, length, totlen, qty, wt = m.groups()
        rows.append(MarkRow(
            mark=mark, diameter=int(dia), shape=shape.strip(),
            segments=[float(a), float(b), float(c), float(d), float(e)],
            length_mm=float(length), total_length_mm=float(totlen),
            qty=int(qty), weight_kg=float(wt),
        ))
    return rows or None


def extract_itemized_bbs_dwg(dxf_path: Path) -> list[MarkRow] | None:
    """Read the itemized "Rebar schedule for X" table(s) directly out of the
    DWG's own paper space, the same way `extract_schedule_dwg` already does
    for the coarser Summary Schedule -- more reliable than PDF text
    extraction (no cell-layout guessing) and works even when a panel has no
    PDF at all.

    Generalizes `parse_itemized_bbs` in two ways the fixed-5-column PDF
    regex can't: (1) the segment-column count varies by sheet (PW-01 uses
    A-E, 5 columns; PW-GF-05 uses A/B/C/D/E/G, 6 -- read from the header
    row itself instead of hardcoding); (2) a panel can carry SEVERAL
    itemized sub-schedules on one sheet (confirmed on PW-GF-05: three
    separate "Rebar schedule for PW-GF-05(A)/(B)/(C)" tables, one per
    physical wing of a multi-part panel) -- every "Rebar schedule for"
    title on the sheet is parsed, tagged with its own `part` suffix.

    Also captures each row's location/cover annotation ("WALL - 30mm",
    "CORBEL - 25mm") when the sheet prints one, off to the right of the
    table at the same row height -- real, useful context (which bars are
    corbel steel vs wall steel) that the PDF text extraction path has no
    equivalent for at all.
    """
    import ezdxf

    try:
        doc = ezdxf.readfile(str(dxf_path))
    except IOError:
        return None

    all_rows: list[MarkRow] = []
    for lname in doc.layout_names():
        if lname.lower() == "model":
            continue
        items = []
        for e in doc.layout(lname):
            if e.dxftype() not in ("MTEXT", "TEXT"):
                continue
            s = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).strip()
            if s:
                items.append((s, e.dxf.insert.x, e.dxf.insert.y))
        titles = [(s, x, y) for s, x, y in items if s.startswith("Rebar schedule for")]
        if not titles:
            continue

        for title, tx, ty in titles:
            m = re.search(r"\(([A-Za-z0-9]+)\)\s*$", title)
            part = m.group(1) if m else ""
            # header row: nearest "Schedule Mark" cell below the title
            hdr_y = hdr_x = None
            for s, x, y in items:
                if s == "Schedule Mark" and y <= ty + 5:
                    if hdr_y is None or y > hdr_y:
                        hdr_y, hdr_x = y, x
            if hdr_y is None:
                continue
            header = sorted(((s, x) for s, x, y in items if abs(y - hdr_y) < 2.0),
                            key=lambda c: c[1])
            labels = [s for s, _x in header]
            if "Shape" not in labels or "Bar Length" not in labels or "Weight" not in labels:
                continue
            # title-block/annotation cells elsewhere on the sheet can share
            # a near-identical Y by coincidence (confirmed: a "<panel>-BBS"
            # title cell landed 0.5 units from one header row) -- truncate
            # at the table's own last real column instead of trusting
            # whatever else this Y-tolerance swept in.
            header = header[:labels.index("Weight") + 1]
            labels = labels[:labels.index("Weight") + 1]
            seg_labels = labels[labels.index("Shape") + 1:labels.index("Bar Length")]
            n_seg = len(seg_labels)
            n_cols = len(labels)
            weight_x = header[labels.index("Weight")][1]
            col_width = (weight_x - hdr_x) / max(n_cols - 1, 1)
            # location annotations (if the sheet prints them, e.g. "WALL -
            # 30mm" / "CORBEL - 25mm") sit further right of the table than
            # first assumed -- confirmed directly on PW-GF-05's own "A1"
            # row: "CORBEL" at weight_x+109, "- 25mm" at weight_x+155, well
            # past a first, too-tight col_width*3 bound that caught nothing
            # real at all. Bounded well short of the title block's own
            # static text (a fixed one-off label elsewhere on the sheet,
            # not printed per-row, so it only risks colliding with a data
            # row that coincidentally shares its exact Y -- confirmed this
            # doesn't happen on the rows actually checked).
            loc_x_lo, loc_x_hi = weight_x + col_width * 0.3, weight_x + col_width * 9.0

            # data rows anchored on the mark column specifically (its own
            # X, +-1/3 column width) -- using ANY nearby-Y text as a row
            # anchor double-counted rows whose location annotation sat at
            # a slightly different Y than the row's own numeric cells.
            mark_x = hdr_x
            mark_ys = sorted({y for s, x, y in items
                              if abs(x - mark_x) < col_width * 0.4 and y < hdr_y - 1},
                             reverse=True)
            for y in mark_ys:
                cells = sorted(((s, x) for s, x, yy in items if abs(yy - y) < 2.0),
                               key=lambda c: c[1])
                table_cells = [(s, x) for s, x in cells if x < weight_x + col_width * 0.3]
                extra = [(s, x) for s, x in cells if loc_x_lo <= x <= loc_x_hi]
                if len(table_cells) < n_cols:
                    continue
                vals = [s for s, _x in table_cells[:n_cols]]
                mark = vals[0]
                if not re.match(r"^[A-Za-z]\w*\d*$", mark):
                    continue
                if not vals[1].endswith(" mm"):
                    continue
                try:
                    dia = int(float(vals[1][:-3]))
                    segs = [float(v[:-3]) for v in vals[3:3 + n_seg]]
                    length_mm = float(vals[3 + n_seg][:-3])
                    total_mm = float(vals[4 + n_seg][:-3])
                    qty = int(vals[5 + n_seg])
                    wt = float(vals[6 + n_seg][:-3]) if vals[6 + n_seg].endswith("kg") \
                        else float(vals[6 + n_seg])
                except (ValueError, IndexError):
                    continue
                # Only accept the specific known location-keyword vocabulary
                # this drawing set actually uses ("WALL", "CORBEL", ...)
                # plus its own "- Nmm" cover continuation -- a bare X-range
                # window alone also swept in unrelated same-row-Y
                # coincidences (title block job numbers, shape-image
                # labels like "M_17A", revision-table text) that have
                # nothing to do with the bar's real location.
                loc_word_re = re.compile(r"^(WALL|CORBEL|MOULD|FACE|SLAB|BEAM|COLUMN)$", re.IGNORECASE)
                loc_cover_re = re.compile(r"^-?\s*\d+\s*mm$", re.IGNORECASE)
                loc_parts = [s for s, _x in extra
                            if loc_word_re.match(s.strip()) or loc_cover_re.match(s.strip())]
                location = " ".join(loc_parts)
                all_rows.append(MarkRow(
                    mark=mark, diameter=dia, shape=vals[2],
                    segments=segs, length_mm=length_mm, total_length_mm=total_mm,
                    qty=qty, weight_kg=wt, location=location, part=part,
                ))
    return all_rows or None


def find_schedule_pdf(dwg_path: Path) -> list[Path]:
    """Candidate schedule PDFs beside a given DWG, tolerating a stray space
    before the extension seen in this drawing set (e.g. "PW-GF-02(R) .pdf")
    and a DWG renamed with a duplicated element id (e.g.
    "PW-01-PW-01(R).dwg" whose real element is "PW-01", matching a sibling
    "PW-01(S).pdf" or "PW-01(R).pdf" that doesn't share the DWG's own stem
    at all). Callers should try each candidate with `extract_schedule` in
    order and use the first that actually yields a table -- a same-stem
    match isn't guaranteed to be the one with the schedule (e.g. the (R)
    elevation PDF vs. a separate (S) schedule-only PDF).
    """
    exact = list(dwg_path.parent.glob(f"{dwg_path.stem}*.pdf"))
    dwg_core = re.sub(r"\([^)]*\)\s*$", "", dwg_path.stem).strip()
    candidates = []
    if dwg_core:
        for p in dwg_path.parent.glob("*.pdf"):
            pdf_core = re.sub(r"\([^)]*\)\s*$", "", p.stem).strip()
            if pdf_core and dwg_core.startswith(pdf_core):
                candidates.append(p)
        # Same-core-length ties (e.g. "(R) .pdf" vs "(S).pdf", both just
        # "PW-GF-09" once parens are stripped) used to fall through to
        # arbitrary filesystem glob order -- confirmed picking the WRONG
        # one on PW-GF-09: its "(R) .pdf" is a genuinely different, OLDER
        # document (373.57kg, dated ~2 months earlier) than the current
        # batch's own "(S).pdf" (328.89kg) -- two real, different
        # revisions of the same panel coexist in this drawing set, not
        # duplicates. A same-batch sibling's file mtime lands within
        # seconds of the source DWG's own (confirmed: the whole PW-GF-05
        # ..31 batch is stamped to the same minute); an older/newer
        # revision's is months off. Rank by mtime proximity to the DWG
        # first -- the right revision, not just "any schedule-shaped
        # file" -- then break remaining ties (rare) toward "(S)" as this
        # set's own naming convention for "the schedule sheet".
        try:
            dwg_mtime = dwg_path.stat().st_mtime
        except OSError:
            dwg_mtime = 0.0

        def is_schedule_named(p: Path) -> int:
            return 0 if re.search(r"\(S\)\s*$", p.stem, re.IGNORECASE) else 1
        candidates.sort(key=lambda p: (
            -len(re.sub(r"\([^)]*\)\s*$", "", p.stem).strip()),
            abs(p.stat().st_mtime - dwg_mtime) if dwg_mtime else 0,
            is_schedule_named(p),
        ))
    # Exact-stem matches first (most likely to be the right sheet), but
    # NEVER return only those and stop -- confirmed on the PW-GF-05..31
    # batch: a same-stem sibling PDF regularly exists (e.g. "(R1).pdf")
    # but is the reinforcement drawing itself, carrying no Summary
    # Schedule table at all; the real schedule lives in a separate
    # "(S).pdf" that only the broader core-prefix search below finds. An
    # early return on `exact` alone silently starved the whole batch of
    # their real official schedule. Callers already try every candidate
    # in order and use the first that actually parses a table, so
    # returning the full combined list (exact matches ranked first) is
    # strictly safer than returning either alone.
    seen = set(exact)
    ordered = list(exact) + [p for p in candidates if p not in seen]
    return ordered


def compare_to_bars(rows: list[ScheduleRow], bars) -> str:
    """Side-by-side official vs. reconstructed weight, per diameter."""
    import math

    def poly_len(pts):
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))

    found: dict[int, float] = {}
    for b in bars:
        found[b.diameter] = found.get(b.diameter, 0.0) + poly_len(b.points)

    official = {r.diameter: r.weight_kg for r in rows}
    all_dia = sorted(set(found) | set(official))
    lines = [f"{'bar':>5} {'reconstructed':>13} {'official':>10} {'gap':>8} {'%':>6}"]
    tot_f = tot_o = 0.0
    for dia in all_dia:
        wf = (found.get(dia, 0.0) / 1000) * dia * dia / 162
        wo = official.get(dia, 0.0)
        tot_f += wf
        tot_o += wo
        pct = f"{100 * wf / wo:.0f}%" if wo else ("extra" if wf else "-")
        lines.append(f"T{dia:<4} {wf:>12.2f}k {wo:>9.2f}k {wf - wo:>+7.2f}k {pct:>6}")
    tot_pct = f"{100 * tot_f / tot_o:.0f}%" if tot_o else "-"
    lines.append(f"{'TOTAL':>5} {tot_f:>12.2f}k {tot_o:>9.2f}k {tot_f - tot_o:>+7.2f}k {tot_pct:>6}")
    return "\n".join(lines)
