"""Extract the itemized Bar Bending Schedule from an (S) DWG.

The (S) sheets carry the schedule as plain MTEXT laid out in a grid on
layer G-ANNO-SCHD in paper space (Layout1) — not a drawn/geometric bar
list. Each panel has 2-3 sub-tables ("Rebar schedule for <panel>(A)",
"(B)", "(C)", ...) which are different *views* of the same physical
panel (per user: "S and R will have the same thing from different
angles or A/B type"), followed by one "Summary Schedule" (per-diameter
totals) that is the panel's own authoritative grand total.

This reads that text directly — no geometry reconstruction — so it is
exact wherever the drawing's own numbers are exact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from dxf_cache import dwg_to_dxf

SCHED_LAYER = "G-ANNO-SCHD"
ROW_TOL = 1.6      # y-clustering tolerance for one table row
HEADER_SPAN = 3.0   # header can wrap onto two closely-spaced y lines
COL_TOL = 12.0      # x tolerance to snap a cell to its column


@dataclass
class BarRow:
    panel: str
    subsheet: str          # 'A' / 'B' / 'C' ...
    mark: str
    dia_mm: float
    shape: str
    segments: dict = field(default_factory=dict)   # {'A': mm, 'B': mm, ...}
    bar_length_mm: float | None = None
    total_length_mm: float | None = None
    quantity: int | None = None
    weight_kg: float | None = None


@dataclass
class SummaryLine:
    dia_mm: float | None   # None = grand-total row
    total_length_mm: float
    weight_kg: float


@dataclass
class ScheduleDoc:
    panel: str
    rows: list = field(default_factory=list)          # list[BarRow]
    summary: list = field(default_factory=list)        # list[SummaryLine]
    source: str = ""


NUM = r"-?\d+(?:\.\d+)?"


def _num(text: str) -> float | None:
    m = re.search(NUM, text.replace(",", ""))
    return float(m.group()) if m else None


def _int(text: str) -> int | None:
    m = re.search(r"-?\d+", text.replace(",", ""))
    return int(m.group()) if m else None


def _load_cells(dxf_path: Path):
    doc = ezdxf.readfile(str(dxf_path))
    cells = []
    for layout_name in doc.layout_names():
        if layout_name == "Model":
            continue
        lay = doc.layouts.get(layout_name)
        for e in lay:
            if e.dxftype() != "MTEXT" or e.dxf.layer != SCHED_LAYER:
                continue
            x, y, _ = e.dxf.insert
            txt = e.plain_text().strip()
            if txt:
                cells.append((round(y, 2), round(x, 2), txt))
    cells.sort(key=lambda t: (-t[0], t[1]))
    return cells


def _cluster_rows(cells, tol=ROW_TOL):
    """Group cells into rows by y, tolerant of tiny jitter."""
    rows = []
    cur = []
    cur_y = None
    for y, x, txt in cells:
        if cur_y is None or abs(y - cur_y) <= tol:
            cur.append((y, x, txt))
            cur_y = y if cur_y is None else cur_y
        else:
            rows.append(cur)
            cur = [(y, x, txt)]
            cur_y = y
    if cur:
        rows.append(cur)
    return rows


TABLE_START_RE = re.compile(r"Rebar schedule for ([\w\-]+)\(([A-Za-z]+)")
SUMMARY_START_RE = re.compile(r"Summary Schedule")
REVISION_HEADER_LABELS = {"Rev", "Date", "Description", "Chkd", "Appd."}
REVISION_TITLE_RE = re.compile(r"REVISION SCHEDULE")


def _strip_revision_block(cells):
    """Drop the title-block's revision-history table.

    It sits in its own x-column region (far right of the sheet) but can
    have a *lower* y than a table's last real data row in cramped
    layouts, so a naive y-ordered "stop at REVISION SCHEDULE" scan
    would truncate real rows. Instead identify the revision block by
    its distinctive column headers and strip anything in that x-range
    outright, independent of y-order.
    """
    xs = [x for _, x, txt in cells if txt.strip() in REVISION_HEADER_LABELS]
    if not xs:
        return cells
    xmin, xmax = min(xs) - 5, max(xs) + 5
    return [(y, x, txt) for y, x, txt in cells if not (xmin <= x <= xmax)]


def parse_schedule_dwg(dwg_path: Path) -> ScheduleDoc:
    dxf_path = dwg_to_dxf(dwg_path)
    cells = _load_cells(dxf_path)
    cells = _strip_revision_block(cells)

    # Segment the flat cell list into blocks: each block starts at a
    # "Rebar schedule for X(Y)" or "Summary Schedule" title cell and
    # runs until the next title.
    blocks = []  # (kind, panel, subsheet, [cells])
    cur_kind = None
    cur_panel = None
    cur_sub = None
    cur_cells = []

    def flush():
        if cur_kind is not None and cur_cells:
            blocks.append((cur_kind, cur_panel, cur_sub, cur_cells))

    for y, x, txt in cells:
        m = TABLE_START_RE.search(txt)
        if m:
            flush()
            cur_kind, cur_panel, cur_sub, cur_cells = "table", m.group(1), m.group(2), []
            continue
        if SUMMARY_START_RE.search(txt):
            flush()
            cur_kind, cur_panel, cur_sub, cur_cells = "summary", cur_panel, None, []
            continue
        if REVISION_TITLE_RE.search(txt):
            flush()
            cur_kind = None
            cur_cells = []
            continue
        if cur_kind is not None:
            cur_cells.append((y, x, txt))
    flush()

    panel_name = dwg_path.stem.split("(")[0]
    doc = ScheduleDoc(panel=panel_name, source=str(dwg_path))

    for kind, panel, sub, block_cells in blocks:
        if kind == "summary":
            doc.summary.extend(_parse_summary_block(block_cells))
        else:
            doc.rows.extend(_parse_table_block(block_cells, panel or panel_name, sub))

    return doc


_DATA_CELL_RE = re.compile(r"^\d+(\.\d+)?\s*(mm|kg)$")


def _row_is_data(row):
    return any(_DATA_CELL_RE.match(txt) for _, _, txt in row)


def _parse_summary_block(cells):
    """3-column table: Bar Diameter | Total Bar Length | Weight, plus a
    final totals row with no diameter. Header may wrap onto >1 line."""
    if not cells:
        return []
    rows = _cluster_rows(cells)
    i = 0
    header = []
    while i < len(rows) and not _row_is_data(rows[i]):
        header.extend(rows[i])
        i += 1
    col_x = sorted({x for _, x, _ in header})
    if len(col_x) < 3:
        return []
    out = []
    for r in rows[i:]:
        r = sorted(r, key=lambda c: c[1])
        vals = {}
        for y, x, txt in r:
            col = min(col_x, key=lambda cx: abs(cx - x))
            vals[col] = txt
        # Use column position robustly: 3 columns sorted by x
        cols_sorted = col_x
        dia_col, len_col, wt_col = cols_sorted[0], cols_sorted[1], cols_sorted[2]
        dia_txt = vals.get(dia_col)
        len_txt = vals.get(len_col)
        wt_txt = vals.get(wt_col)
        dia_val = _num(dia_txt) if dia_txt else None
        len_val = _num(len_txt) if len_txt else None
        wt_val = _num(wt_txt) if wt_txt else None
        if len_val is None or wt_val is None:
            continue
        out.append(SummaryLine(dia_mm=dia_val, total_length_mm=len_val, weight_kg=wt_val))
    return out


def _parse_table_block(cells, panel, sub):
    if not cells:
        return []
    rows = _cluster_rows(cells)
    if not rows:
        return []
    # Header may span two adjacent clustered rows (wrapped column titles).
    header_cells = list(rows[0])
    data_start = 1
    if len(rows) > 1:
        y0 = rows[0][0][0]
        y1 = rows[1][0][0]
        if abs(y0 - y1) <= HEADER_SPAN:
            header_cells += rows[1]
            data_start = 2

    # Build column map: x -> label
    columns = {}
    for y, x, txt in header_cells:
        columns[round(x, 1)] = columns.get(round(x, 1), "")
        columns[round(x, 1)] = (columns[round(x, 1)] + " " + txt).strip()
    col_xs = sorted(columns)

    def colname_at(x):
        cx = min(col_xs, key=lambda c: abs(c - x))
        if abs(cx - x) > COL_TOL:
            return None, cx
        return columns[cx], cx

    out = []
    for r in rows[data_start:]:
        vals = {}
        for y, x, txt in r:
            name, cx = colname_at(x)
            if name is None:
                continue  # stray text outside this table's column range (e.g. an unrelated block sharing this row's y)
            vals[name] = txt
        if not vals:
            continue
        # a "subtotal" row has only Total/Quantity/Weight populated (no mark)
        mark = None
        dia = None
        shape = None
        for name, txt in vals.items():
            lname = name.lower()
            if "mark" in lname:
                mark = txt
            elif "diameter" in lname:
                dia = _num(txt)
            elif lname == "shape":
                shape = txt
        if mark is None:
            continue  # subtotal / stray row, not an individual bar row

        segs = {}
        for name, txt in vals.items():
            if len(name) == 1 and name.isalpha():
                v = _num(txt)
                if v is not None:
                    segs[name] = v

        bar_length = None
        total_length = None
        qty = None
        weight = None
        for name, txt in vals.items():
            lname = name.lower()
            if lname == "bar length":
                bar_length = _num(txt)
            elif "total bar" in lname or lname == "total bar length":
                total_length = _num(txt)
            elif lname == "quantity":
                qty = _int(txt)
            elif lname == "weight":
                weight = _num(txt)

        out.append(BarRow(
            panel=panel, subsheet=sub, mark=mark, dia_mm=dia, shape=shape or "",
            segments=segs, bar_length_mm=bar_length, total_length_mm=total_length,
            quantity=qty, weight_kg=weight,
        ))
    return out


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1])
    doc = parse_schedule_dwg(p)
    print(f"Panel {doc.panel}: {len(doc.rows)} bar rows")
    for r in doc.rows:
        print(f"  [{r.subsheet}] {r.mark:>4} T{r.dia_mm:.0f} qty={r.quantity} "
              f"len={r.bar_length_mm}mm total={r.total_length_mm}mm wt={r.weight_kg}kg")
    print("Summary:")
    for s in doc.summary:
        print(f"  dia={s.dia_mm} total_len={s.total_length_mm}mm wt={s.weight_kg}kg")
