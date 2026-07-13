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

    def add(e, ox: float = 0.0, oy: float = 0.0) -> None:
        t = e.dxftype()
        layer = e.dxf.layer
        if t == "LINE":
            s, d = e.dxf.start, e.dxf.end
            ents.append(Ent("LINE", layer, points=[(s.x + ox, s.y + oy), (d.x + ox, d.y + oy)]))
        elif t == "ARC":
            c = e.dxf.center
            ents.append(
                Ent(
                    "ARC",
                    layer,
                    center=(c.x + ox, c.y + oy),
                    radius=e.dxf.radius,
                    start_angle=e.dxf.start_angle,
                    end_angle=e.dxf.end_angle,
                )
            )
        elif t == "CIRCLE":
            c = e.dxf.center
            ents.append(Ent("CIRCLE", layer, center=(c.x + ox, c.y + oy), radius=e.dxf.radius))
        elif t == "LWPOLYLINE":
            pts = [(p[0] + ox, p[1] + oy) for p in e.get_points()]
            ents.append(Ent("LWPOLYLINE", layer, points=pts, closed=bool(e.closed)))
        elif t == "POLYLINE":
            try:
                pts = [(v.dxf.location.x + ox, v.dxf.location.y + oy) for v in e.vertices]
            except Exception:
                return
            ents.append(Ent("LWPOLYLINE", layer, points=pts, closed=e.is_closed))
        elif t in ("MTEXT", "TEXT"):
            ip = e.dxf.insert if t == "MTEXT" else e.dxf.insert
            txt = _mtext_plain(e) if t == "MTEXT" else e.dxf.text
            ents.append(Ent(t, layer, points=[(ip.x + ox, ip.y + oy)], text=txt))
        elif t == "INSERT" and explode_inserts:
            try:
                for sub in e.virtual_entities():
                    add(sub)
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
