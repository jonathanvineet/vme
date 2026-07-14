"""Load DXF files (converted from DWG) and flatten entities into simple records."""
from __future__ import annotations

import math
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.math import Vec3


@dataclass
class Ent:
    """A flattened drawing entity: geometry reduced to points/segments."""

    kind: str  # LINE | ARC | CIRCLE | LWPOLYLINE | MTEXT | TEXT | DIMENSION | HATCH | INSERT
    layer: str
    # geometry
    points: list[tuple[float, float]] = field(default_factory=list)  # polyline vertices / line endpoints
    center: tuple[float, float] | None = None  # arc / circle
    radius: float = 0.0
    start_angle: float = 0.0  # degrees, arcs
    end_angle: float = 0.0
    text: str = ""  # mtext/text content
    closed: bool = False
    ltype: str = ""  # resolved linetype, lowercase ("" = continuous)
    block: str = ""  # source block name for geometry exploded from an INSERT
    bref: int = -1  # unique id per INSERT instance (groups exploded geometry)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs, ys = [], []
        for x, y in self.points:
            xs.append(x)
            ys.append(y)
        if self.center is not None:
            cx, cy = self.center
            xs += [cx - self.radius, cx + self.radius]
            ys += [cy - self.radius, cy + self.radius]
        if not xs:
            return (0, 0, 0, 0)
        return (min(xs), min(ys), max(xs), max(ys))


def dwg_to_dxf(dwg_path: Path, out_dir: Path) -> Path:
    """Convert a DWG to DXF using libredwg's dwg2dxf."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (dwg_path.stem + ".dxf")
    if not out.exists() or out.stat().st_mtime < dwg_path.stat().st_mtime:
        subprocess.run(
            ["dwg2dxf", "-o", str(out), str(dwg_path)],
            check=True,
            capture_output=True,
        )
    return out


def _mtext_plain(e) -> str:
    try:
        return e.plain_text()
    except Exception:
        return getattr(e.dxf, "text", "") or ""


def load_entities(dxf_path: Path, explode_inserts: bool = True) -> list[Ent]:
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    ents: list[Ent] = []
    layer_lt = {l.dxf.name: (l.dxf.linetype or "") for l in doc.layers}
    next_bref = [0]

    def ltype_of(e) -> str:
        lt = getattr(e.dxf, "linetype", "") or ""
        if lt.upper() in ("BYLAYER", "BYBLOCK", ""):
            lt = layer_lt.get(e.dxf.layer, "")
        return "" if lt.lower() == "continuous" else lt.lower()

    def add(e, block: str = "", bref: int = -1) -> None:
        t = e.dxftype()
        layer = e.dxf.layer
        lt = ltype_of(e)
        if t == "LINE":
            s, d = e.dxf.start, e.dxf.end
            ents.append(Ent("LINE", layer, points=[(s.x, s.y), (d.x, d.y)],
                            ltype=lt, block=block, bref=bref))
        elif t == "ARC":
            c = e.dxf.center
            ents.append(
                Ent(
                    "ARC",
                    layer,
                    center=(c.x, c.y),
                    radius=e.dxf.radius,
                    start_angle=e.dxf.start_angle,
                    end_angle=e.dxf.end_angle,
                    ltype=lt, block=block, bref=bref,
                )
            )
        elif t == "CIRCLE":
            c = e.dxf.center
            ents.append(Ent("CIRCLE", layer, center=(c.x, c.y), radius=e.dxf.radius,
                            ltype=lt, block=block, bref=bref))
        elif t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            ents.append(Ent("LWPOLYLINE", layer, points=pts, closed=bool(e.closed),
                            ltype=lt, block=block, bref=bref))
        elif t == "POLYLINE":
            try:
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            except Exception:
                return
            ents.append(Ent("LWPOLYLINE", layer, points=pts, closed=e.is_closed,
                            ltype=lt, block=block, bref=bref))
        elif t in ("MTEXT", "TEXT"):
            ip = e.dxf.insert
            txt = _mtext_plain(e) if t == "MTEXT" else e.dxf.text
            ents.append(Ent(t, layer, points=[(ip.x, ip.y)], text=txt,
                            ltype=lt, block=block, bref=bref))
        elif t == "INSERT" and explode_inserts:
            # geometry from nested inserts keeps the outermost instance id
            name = block or e.dxf.name
            ref = bref if bref >= 0 else next_bref[0]
            if bref < 0:
                next_bref[0] += 1
            try:
                for sub in e.virtual_entities():
                    add(sub, block=name, bref=ref)
            except Exception:
                pass

    for e in msp:
        add(e)
    return ents


def arc_points(ent: Ent, n: int = 16) -> list[tuple[float, float]]:
    """Sample an ARC entity into a polyline."""
    a0 = math.radians(ent.start_angle)
    a1 = math.radians(ent.end_angle)
    if a1 <= a0:
        a1 += 2 * math.pi
    cx, cy = ent.center
    return [
        (cx + ent.radius * math.cos(a0 + (a1 - a0) * i / n), cy + ent.radius * math.sin(a0 + (a1 - a0) * i / n))
        for i in range(n + 1)
    ]
