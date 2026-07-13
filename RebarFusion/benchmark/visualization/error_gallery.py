"""
benchmark/visualization/error_gallery.py — one image per identity error.

Renders observation bounding boxes for the observations involved in each
failure, colored by which ground-truth bar they belong to versus which
pipeline identity claimed them. Existence-level visualization only — it
shows WHICH observations were grouped wrongly, in their own drawing's
coordinates, not reconstructed geometry.

Returns PNG bytes (embedded base64 in the HTML report so report.html
stays self-contained); also written as files alongside the report.
"""
from __future__ import annotations

import io
from typing import Dict, List, Optional


def render_error_image(title: str, groups: Dict[str, List], note: str = "") -> Optional[bytes]:
    """groups: label -> list of PhysicalObservation. Returns PNG bytes, or
    None when nothing is drawable (no observations, degenerate bboxes, or
    matplotlib unavailable)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except Exception:
        return None

    drawable = {
        label: [o for o in obs if o.bbox and (o.bbox[2] - o.bbox[0] or o.bbox[3] - o.bbox[1])]
        for label, obs in groups.items()
    }
    if not any(drawable.values()):
        return None

    colors = ["#e6553a", "#3a7be6", "#3ae67c", "#e6c53a", "#a53ae6", "#3ae6d9"]
    fig, ax = plt.subplots(figsize=(8, 5))
    handles = []
    for idx, (label, obs_list) in enumerate(sorted(drawable.items())):
        color = colors[idx % len(colors)]
        for o in obs_list:
            x0, y0, x1, y1 = o.bbox
            ax.add_patch(mpatches.Rectangle(
                (x0, y0), x1 - x0, y1 - y0,
                fill=False, edgecolor=color, linewidth=1.5,
            ))
            mark = o.fact("mark")
            ax.annotate(
                f"{mark.value if mark else '?'}\n{o.drawing_filename}",
                ((x0 + x1) / 2, (y0 + y1) / 2),
                ha="center", va="center", fontsize=6, color=color,
            )
        handles.append(mpatches.Patch(edgecolor=color, fill=False, label=label))

    ax.legend(handles=handles, fontsize=7, loc="upper right")
    ax.set_title(title, fontsize=9)
    if note:
        ax.set_xlabel(note, fontsize=7)
    ax.autoscale_view()
    ax.set_aspect("equal", adjustable="datalim")
    ax.relim()
    ax.autoscale()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
