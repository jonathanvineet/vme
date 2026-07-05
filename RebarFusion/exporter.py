"""Export detected rebars to CSV/JSON and produce annotated image."""
from __future__ import annotations

import csv
import json
import logging
import os
from typing import List

import matplotlib.pyplot as plt
from PIL import Image
import numpy as np

from shapely.geometry import LineString

from rebar_detector import Rebar

logger = logging.getLogger(__name__)


class Exporter:
    def __init__(self, out_dir: str = "output"):
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

    def export_csv(self, rebars: List[Rebar], filename: str = "rebars.csv") -> None:
        path = os.path.join(self.out_dir, filename)
        fieldnames = [
            'id', 'start_x', 'start_y', 'end_x', 'end_y', 'center_x', 'center_y', 'length', 'angle', 'bbox'
        ]
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rebars:
                writer.writerow({
                    'id': r.id,
                    'start_x': r.start[0],
                    'start_y': r.start[1],
                    'end_x': r.end[0],
                    'end_y': r.end[1],
                    'center_x': r.center[0],
                    'center_y': r.center[1],
                    'length': r.length,
                    'angle': r.angle,
                    'bbox': f"{r.bbox}",
                })
        logger.info("Wrote CSV to %s", path)

    def export_json(self, rebars: List[Rebar], filename: str = "rebars.json") -> None:
        path = os.path.join(self.out_dir, filename)
        payload = [r.__dict__ for r in rebars]
        # ensure serializable
        for p in payload:
            p['bbox'] = list(p.get('bbox', []))
            p['start'] = list(p.get('start', []))
            p['end'] = list(p.get('end', []))
            p['center'] = list(p.get('center', []))
        with open(path, 'w') as f:
            json.dump(payload, f, indent=2)
        logger.info("Wrote JSON to %s", path)

    def export_preview(self, rebars: List[Rebar], filename: str = "preview.png", width: int = 1200, height: int = 1200, dpi: int = 100):
        out_path = os.path.join(self.out_dir, filename)
        all_bounds = [r.bbox for r in rebars]
        if not all_bounds:
            raise ValueError("No rebars to draw")

        minx = min(b[0] for b in all_bounds)
        miny = min(b[1] for b in all_bounds)
        maxx = max(b[2] for b in all_bounds)
        maxy = max(b[3] for b in all_bounds)

        pad_x = (maxx - minx) * 0.05 if maxx > minx else 10.0
        pad_y = (maxy - miny) * 0.05 if maxy > miny else 10.0

        fig_w = width / dpi
        fig_h = height / dpi

        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        ax.set_xlim(minx - pad_x, maxx + pad_x)
        ax.set_ylim(miny - pad_y, maxy + pad_y)
        ax.set_aspect('equal')
        ax.invert_yaxis()
        ax.axis('off')

        for r in rebars:
            # some Rebar objects store segments list rather than shapely geom
            if hasattr(r, 'geom') and r.geom is not None:
                coords = list(r.geom.coords)
            else:
                # fallback: use start/end
                coords = [tuple(r.start), tuple(r.end)]
            xs, ys = zip(*coords)
            ax.plot(xs, ys, '-b', linewidth=2)
            ax.text(r.center[0], r.center[1], str(r.id), color='red', fontsize=8, weight='bold')

        fig.tight_layout(pad=0)
        fig.savefig(out_path, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        logger.info("Saved annotated image to %s", out_path)
