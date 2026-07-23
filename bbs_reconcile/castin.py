"""Extract cast-in items (sleeves/corrugated pipes, corbels, anchors)
from an (R) or (M) DWG, for the 3D viewer.

Conventions confirmed by direct DXF inspection (2026-07-23), consistent
with what the sibling rebar3d project independently documented for the
same drawing set:
  - Sleeves (corrugated pipes) = circles on layer A-WALL, drawn as ARC
    fragments rather than one whole CIRCLE entity (confirmed: PW-GF-02(R)
    has 143 A-WALL arcs, 140 at radius 25mm [N4/50mm-dia sleeve], 3 at
    radius 10mm [N5/20mm-dia]). Accumulate arcs sharing a (center,
    radius) and accept as a real sleeve once their angular coverage is
    substantial (>=120 degrees combined) - a single stray arc fragment
    from unrelated linework isn't enough evidence on its own.
  - Corbels / cast-in hardware = block INSERTs on A-GENM / S-BEAM layers
    (e.g. "M_Rectangular Corbel", "RR spread anchor...", "loopbox...
    Wire Loop", "M_Linear Stiffener-Channel..."). Their instance
    bounding box in the elevation gives real X/Y footprint.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from dxf_cache import dwg_to_dxf

SLEEVE_RADIUS_TOL = 3.0
SLEEVE_CENTER_TOL = 15.0
SLEEVE_MIN_COVERAGE_DEG = 100.0

CORBEL_KEYWORDS = ("corbel", "anchor", "loopbox", "stiffener", "channel", "insert")


@dataclass
class Sleeve:
    x: float
    y: float
    radius_mm: float


@dataclass
class CastInBlock:
    name: str
    kind: str        # "corbel" | "anchor" | "channel" | "other"
    x0: float
    y0: float
    x1: float
    y1: float


def _classify_block(name: str) -> str:
    n = name.lower()
    if "corbel" in n:
        return "corbel"
    if "anchor" in n or "loopbox" in n:
        return "anchor"
    if "stiffener" in n or "channel" in n:
        return "channel"
    return "other"


def extract_sleeves(dwg_path: Path, elev_bbox) -> list[Sleeve]:
    dxf_path = dwg_to_dxf(dwg_path)
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    ex0, ex1, ey0, ey1 = elev_bbox
    margin = 50.0

    # group raw arcs by rounded (center, radius)
    groups: dict[tuple, list[tuple[float, float]]] = {}
    for e in msp:
        if e.dxftype() != "ARC" or e.dxf.layer != "A-WALL":
            continue
        cx, cy, _ = e.dxf.center
        if not (ex0 - margin <= cx <= ex1 + margin and ey0 - margin <= cy <= ey1 + margin):
            continue
        r = e.dxf.radius
        key = (round(cx / SLEEVE_CENTER_TOL), round(cy / SLEEVE_CENTER_TOL), round(r / SLEEVE_RADIUS_TOL))
        groups.setdefault(key, []).append((e.dxf.start_angle, e.dxf.end_angle, cx, cy, r))

    sleeves = []
    for key, arcs in groups.items():
        coverage = 0.0
        for a0, a1, *_ in arcs:
            span = (a1 - a0) % 360
            coverage += span
        if coverage >= SLEEVE_MIN_COVERAGE_DEG:
            cx = sum(a[2] for a in arcs) / len(arcs)
            cy = sum(a[3] for a in arcs) / len(arcs)
            r = sum(a[4] for a in arcs) / len(arcs)
            sleeves.append(Sleeve(cx, cy, r))
    return sleeves


def extract_castin_blocks(dwg_path: Path, elev_bbox, own_bbox=None) -> list[CastInBlock]:
    """own_bbox: this DWG's own elevation bbox (may differ from elev_bbox
    if this is a separate M-sheet file with its own sheet coordinates) -
    used to remap positions proportionally onto elev_bbox's frame, the
    same technique used for horizontal section-cut Z evidence."""
    dxf_path = dwg_to_dxf(dwg_path)
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    ex0, ex1, ey0, ey1 = elev_bbox
    if own_bbox is None:
        own_bbox = elev_bbox
    ox0, ox1, oy0, oy1 = own_bbox
    ow, oh = max(ox1 - ox0, 1e-6), max(oy1 - oy0, 1e-6)
    margin = 300.0

    def remap(ix, iy):
        fx = (ix - ox0) / ow
        fy = (iy - oy0) / oh
        return ex0 + fx * (ex1 - ex0), ey0 + fy * (ey1 - ey0)

    out = []
    for e in msp:
        if e.dxftype() != "INSERT" or e.dxf.layer not in ("A-GENM", "S-BEAM"):
            continue
        name = e.dxf.name
        low = name.lower()
        if not any(k in low for k in CORBEL_KEYWORDS):
            continue
        ix0, iy0, _ = e.dxf.insert
        if not (ox0 - margin <= ix0 <= ox1 + margin and oy0 - margin <= iy0 <= oy1 + margin):
            continue
        ix, iy = remap(ix0, iy0)
        try:
            blk = doc.blocks.get(name)
        except Exception:
            continue
        xs, ys = [], []
        for be in blk:
            if be.dxftype() == "LINE":
                xs += [be.dxf.start[0], be.dxf.end[0]]
                ys += [be.dxf.start[1], be.dxf.end[1]]
        if not xs:
            # fall back to a small marker footprint at the insertion point
            xs, ys = [-75, 75], [-75, 75]
        scale_x = (getattr(e.dxf, "xscale", 1.0) or 1.0) * (ex1 - ex0) / ow
        scale_y = (getattr(e.dxf, "yscale", 1.0) or 1.0) * (ey1 - ey0) / oh
        wx0, wx1 = min(xs) * scale_x, max(xs) * scale_x
        wy0, wy1 = min(ys) * scale_y, max(ys) * scale_y
        # ignore rotation for the bounding box (corbels/anchors are near axis-aligned
        # in these drawings) - good enough for a footprint marker, not exact outline
        x0, x1 = ix + min(wx0, wx1), ix + max(wx0, wx1)
        y0, y1 = iy + min(wy0, wy1), iy + max(wy0, wy1)
        if x1 - x0 < 1 or y1 - y0 < 1:
            continue
        out.append(CastInBlock(name, _classify_block(name), x0, y0, x1, y1))
    return out
