from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


class DebugOverlay:
    def __init__(self):
        self.colors = {}

    def color(self, family_id):
        if family_id not in self.colors:
            cmap = plt.get_cmap("tab20")
            index = len(self.colors) % cmap.N
            self.colors[family_id] = cmap(index)
        return self.colors[family_id]

    def draw(self, families, output):
        fig, ax = plt.subplots(figsize=(16, 12), dpi=150)
        ax.set_aspect("equal")

        all_boxes = []

        for fam in families:
            family_id = fam["family"]
            c = self.color(family_id)
            bars = fam.get("bars", [])

            for bar in bars:
                bbox = bar.get("bbox")
                insert = bar.get("insert")
                direction = bar.get("direction", "Unknown")

                if not bbox:
                    continue

                x0, y0, x1, y1 = bbox
                all_boxes.append((x0, y0, x1, y1))

                rect = Rectangle(
                    (x0, y0),
                    x1 - x0,
                    y1 - y0,
                    fill=False,
                    edgecolor=c,
                    linewidth=1.4,
                    alpha=0.9,
                )
                ax.add_patch(rect)

                if insert is not None:
                    ax.scatter(insert[0], insert[1], s=12, color=c)
                    ax.text(
                        insert[0],
                        insert[1],
                        f"[{family_id}]",
                        fontsize=8,
                        color=c,
                        weight="bold",
                        ha="center",
                        va="center",
                        bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor=c, alpha=0.7),
                    )

                cx = (x0 + x1) / 2.0
                cy = (y0 + y1) / 2.0
                ax.text(
                    cx,
                    cy,
                    direction,
                    fontsize=6,
                    color=c,
                    ha="center",
                    va="bottom",
                )

        if all_boxes:
            minx = min(b[0] for b in all_boxes)
            miny = min(b[1] for b in all_boxes)
            maxx = max(b[2] for b in all_boxes)
            maxy = max(b[3] for b in all_boxes)
            pad_x = max((maxx - minx) * 0.05, 10.0)
            pad_y = max((maxy - miny) * 0.05, 10.0)
            ax.set_xlim(minx - pad_x, maxx + pad_x)
            ax.set_ylim(miny - pad_y, maxy + pad_y)

        ax.invert_yaxis()
        ax.axis("off")
        fig.tight_layout(pad=0)
        fig.savefig(output, dpi=300, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
