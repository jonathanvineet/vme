"""Extract bar callouts from an (R) rebar-layout DWG.

R sheets don't repeat the schedule mark letters (A, B, C...) next to the
bars — they carry independent count/diameter/pitch callouts on layer
S-RBAR-IDEN, e.g. "2 -T12", "T8 UBAR @125 mm", "2 -T16 CRACK BAR".
These are used as corroborating evidence for the (S) schedule rows, not
as a replacement tally (a callout can repeat across multiple views of
the same physical bars, so raw counts over-count real bar quantity).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import ezdxf

from dxf_cache import dwg_to_dxf

IDEN_LAYER = "S-RBAR-IDEN"

# Two callout styles seen across sheets: "2 -T12 Crack Bar" and the
# parenthesised "-(14) -(T12)" / "-(61) -(T8 U Bar)" / "-(2)-T16 Perimeter Bar"
# form. Stripping parens first unifies both onto one pattern.
COUNT_DIA_RE = re.compile(r"^-?\s*(\d+)\s*-\s*T(\d+)\s*(.*)$", re.IGNORECASE)
DIA_PITCH_RE = re.compile(r"^T(\d+)\s*(UBAR|U\s*BAR|TIE[S]?|HOOK)?\s*@\s*(\d+)\s*mm\s*(.*)$", re.IGNORECASE)
BARE_DIA_RE = re.compile(r"^T(\d+)$", re.IGNORECASE)
# A lone schedule-mark leader label near a callout (e.g. "F", "B1", "I1") —
# informational, not itself a diameter callout.
MARK_RE = re.compile(r"^[A-Z]{1,2}\d{0,2}$")


@dataclass
class Callout:
    text: str
    dia_mm: float
    count: int | None      # None if this is a pitch callout (spacing, not an absolute count)
    pitch_mm: float | None
    note: str
    x: float
    y: float
    source: str


def _iter_texts(dxf_path: Path):
    doc = ezdxf.readfile(str(dxf_path))
    for layout_name in doc.layout_names():
        lay = doc.layouts.get(layout_name)
        for e in lay:
            if e.dxf.layer != IDEN_LAYER:
                continue
            if e.dxftype() == "MTEXT":
                txt = e.plain_text().strip()
                x, y, _ = e.dxf.insert
            elif e.dxftype() == "TEXT":
                txt = e.dxf.text.strip()
                x, y, _ = e.dxf.insert
            else:
                continue
            if txt:
                yield x, y, txt


def parse_callouts(dwg_path: Path) -> list[Callout]:
    dxf_path = dwg_to_dxf(dwg_path)
    out = []
    for x, y, txt in _iter_texts(dxf_path):
        norm = txt.replace("\n", " ").strip()
        stripped = norm.replace("(", "").replace(")", "").strip()
        stripped = re.sub(r"\s+", " ", stripped)

        m = COUNT_DIA_RE.match(stripped)
        if m:
            count, dia, note = int(m.group(1)), float(m.group(2)), m.group(3).strip()
            out.append(Callout(norm, dia, count, None, note, x, y, str(dwg_path)))
            continue
        m = DIA_PITCH_RE.match(norm)
        if m:
            dia = float(m.group(1))
            kind = (m.group(2) or "").strip()
            pitch = float(m.group(3))
            note = (kind + " " + (m.group(4) or "")).strip()
            out.append(Callout(norm, dia, None, pitch, note, x, y, str(dwg_path)))
            continue
        m = BARE_DIA_RE.match(norm)
        if m:
            out.append(Callout(norm, float(m.group(1)), 1, None, "", x, y, str(dwg_path)))
            continue
        if MARK_RE.match(norm):
            # a schedule-mark leader label sitting next to a callout, not a
            # diameter callout itself
            out.append(Callout(norm, float("nan"), None, None, "MARK_REF", x, y, str(dwg_path)))
            continue
        # unrecognized text on the identifier layer - keep for visibility
        out.append(Callout(norm, float("nan"), None, None, "UNPARSED", x, y, str(dwg_path)))
    return out


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(f"=== {p} ===")
        for c in parse_callouts(Path(p)):
            print(f"  dia={c.dia_mm} count={c.count} pitch={c.pitch_mm} note={c.note!r} text={c.text!r}")
