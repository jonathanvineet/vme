"""Export a reconstructed panel: model JSON, 2D projection PNGs, 3D HTML viewer."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from .reconstruct import Panel

ASSETS = Path(__file__).parent

DIA_COLORS = {
    6: "#b0b0b0", 8: "#e15759", 10: "#f28e2b", 12: "#59a14f",
    16: "#af7aa1", 20: "#4e79a7", 25: "#9c755f", 32: "#e377c2",
}


def panel_to_dict(p: Panel) -> dict:
    return {
        "name": p.name,
        "width": round(p.width, 1),
        "height": round(p.height, 1),
        "thickness": round(p.thickness, 1),
        "openings": [[[round(x, 1), round(y, 1)] for x, y in lp] for lp in p.openings],
        "bars": [
            {
                "d": b.diameter,
                "kind": b.kind,
                "z_src": b.z_source,
                "pts": [[round(x, 1), round(y, 1), round(z, 1)] for x, y, z in b.points],
            }
            for b in p.bars
        ],
        "stats": p.stats,
        "families": p.families,
        "features": [
            {
                "kind": f.kind,
                "box": [round(v, 1) for v in f.box] if f.box else None,
                "center": [round(f.center[0], 1), round(f.center[1], 1)] if f.center else None,
                "r": round(f.radius, 1),
                "label": f.label,
            }
            for f in p.features
        ],
    }


def write_json(p: Panel, out: Path) -> None:
    out.write_text(json.dumps(panel_to_dict(p)))


def write_projections(p: Panel, out: Path) -> None:
    """Three orthographic projections: front (XY), top (XZ), side (ZY)."""
    fig, axes = plt.subplots(
        2, 2, figsize=(16, 12),
        gridspec_kw={"width_ratios": [4, 1], "height_ratios": [4, 1]},
    )
    ax_front, ax_side, ax_top, ax_off = axes[0][0], axes[0][1], axes[1][0], axes[1][1]
    ax_off.axis("off")

    FEAT_COLORS = {"corbel": "#8a919d", "embed": "#5c6470", "anchor": "#f28e2b", "loop": "#f28e2b"}

    def draw(ax, ix, iy, title, box):
        ax.add_patch(mpatches.Rectangle((0, 0), box[0], box[1], fill=False, color="#1f77b4", lw=1.2))
        for b in p.bars:
            xs = [pt[ix] for pt in b.points]
            ys = [pt[iy] for pt in b.points]
            ax.plot(xs, ys, color=DIA_COLORS.get(b.diameter, "#333"), lw=0.7)
        for f in p.features:
            if f.kind == "sleeve" and f.center is not None:
                c3 = (f.center[0], f.center[1], p.thickness / 2)
                if ix == 0 and iy == 1:
                    ax.add_patch(mpatches.Circle((c3[0], c3[1]), f.radius, fill=False, color="#2ecc71", lw=1.2))
                else:
                    u, v = c3[ix], c3[iy]
                    half = p.thickness / 2
                    du = half if ix == 2 else 0
                    dv = half if iy == 2 else 0
                    ax.plot([u - du, u + du], [v - dv, v + dv], color="#2ecc71", lw=1.2)
            elif f.box is not None:
                x0, y0, z0, x1, y1, z1 = f.box
                lo = (x0, y0, z0)
                hi = (x1, y1, z1)
                ax.add_patch(mpatches.Rectangle(
                    (lo[ix], lo[iy]), hi[ix] - lo[ix], hi[iy] - lo[iy],
                    fill=False, color=FEAT_COLORS.get(f.kind, "#999"), lw=1.2))
        if ix == 0 and iy == 1:
            for lp in p.openings:
                ax.add_patch(mpatches.Polygon(lp, fill=False, color="#17becf", lw=1.0))
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=9)
        ax.autoscale()

    draw(ax_front, 0, 1, f"{p.name} — front (X/Y)", (p.width, p.height))
    draw(ax_side, 2, 1, "side (Z/Y)", (p.thickness, p.height))
    draw(ax_top, 0, 2, "top (X/Z)", (p.width, p.thickness))
    handles = [
        plt.Line2D([0], [0], color=c, lw=2, label=f"T{d}")
        for d, c in DIA_COLORS.items()
        if any(b.diameter == d for b in p.bars)
    ]
    ax_off.legend(handles=handles, loc="center", fontsize=10, title="Bar dia")
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_viewer(panels: list[Panel], out: Path, title: str = "Rebar 3D") -> None:
    three_src = (ASSETS / "assets_three.js").read_text()
    models = json.dumps([panel_to_dict(p) for p in panels])
    html = (
        VIEWER_TEMPLATE
        .replace("__TITLE__", title)
        .replace("__THREE_JS__", three_src)
        .replace("__MODELS__", models)
    )
    out.write_text(html)


VIEWER_TEMPLATE = (ASSETS / "viewer_template.html").read_text()
