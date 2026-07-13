"""Debug rendering of entity sets / views to PNG via matplotlib."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .loader import Ent, arc_points

LAYER_COLORS = {
    "S-RBAR": "#d62728",
    "S-RBAR-IDEN": "#ff9896",
    "A-WALL": "#1f77b4",
    "A-WALL-HDLN": "#aec7e8",
    "S-BEAM": "#2ca02c",
}


def draw_ents(ax, ents: list[Ent], lw: float = 0.4) -> None:
    for e in ents:
        color = LAYER_COLORS.get(e.layer, "#999999")
        if e.kind == "LINE" or e.kind == "LWPOLYLINE":
            pts = e.points + ([e.points[0]] if e.closed and e.points else [])
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(xs, ys, color=color, lw=lw)
        elif e.kind == "ARC":
            pts = arc_points(e)
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, lw=lw)
        elif e.kind == "CIRCLE":
            ax.add_patch(plt.Circle(e.center, e.radius, fill=False, color=color, lw=lw))
        elif e.kind in ("MTEXT", "TEXT") and e.points:
            ax.annotate(
                e.text[:24], e.points[0], fontsize=2.5, color="#444444", clip_on=True
            )


def render(ents: list[Ent], out_png: Path, title: str = "", dpi: int = 200) -> None:
    fig, ax = plt.subplots(figsize=(16, 10))
    draw_ents(ax, ents)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)
    ax.autoscale()
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
