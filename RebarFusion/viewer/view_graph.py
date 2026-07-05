"""
debug_viewer.py  —  2D Engineering Debugger

Renders the CAD topology graph directly over the original DXF geometry.
Supports component navigation, toggleable overlays, and node degree visualization.

Usage:
    PYTHONPATH=. python3 debug_viewer.py <drawing.dxf>

Keyboard shortcuts:
    N / →      Next component
    P / ←      Previous component
    A          Select All (show all components)
    T          Toggle topology graph
    G          Toggle DXF raw geometry
    B          Toggle bounding boxes
    D          Toggle node degrees
    L          Toggle component labels
    R          Reset view (fit all)
"""

import sys
import os
import argparse
import math
from typing import List, Dict, Tuple, Optional

import matplotlib
matplotlib.use("MacOSX")        # native macOS backend for best interactivity
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D
from matplotlib.widgets import Button, CheckButtons
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from core.engine import GeometryEngine
from core.topology.graph import ConnectedComponent, TopologyGraph
from core.topology.canonical import CanonicalNode
from core.geometry.entities import LineEntity, ArcEntity, PolylineEntity
from core.geometry.repository import GeometryRepository

# ─── Colour scheme ────────────────────────────────────────────────────────────
DEGREE_COLORS = {
    1: "#FF4444",   # endpoint  — red
    2: "#44FF88",   # chain     — green
}
DEGREE_DEFAULT = "#4488FF"       # intersection 3+ — blue

BG_COLOR   = "#0D0D0D"
GEO_COLOR  = "#2A2A3A"
SEL_COLOR  = "#FFD700"           # selected component — gold
UNSEL_COLOR = "#1A3A5C"         # unselected components — muted blue
BBOX_COLOR = "#FF8800"
TEXT_COLOR = "#CCCCCC"


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _comp_bbox(comp: ConnectedComponent, node_map: Dict[int, CanonicalNode]) -> Tuple[float, float, float, float]:
    xs = [node_map[n].point.x for n in comp.nodes if n in node_map]
    ys = [node_map[n].point.y for n in comp.nodes if n in node_map]
    if not xs:
        return (0, 0, 0, 0)
    return min(xs), min(ys), max(xs), max(ys)

def _comp_length(comp: ConnectedComponent) -> float:
    return sum(e.length for e in comp.edges)


# ─── Main Debugger ───────────────────────────────────────────────────────────
class DebugViewer:
    def __init__(self, context):
        self.context  = context
        self.repo     = context.repository
        self.graph    = context.topology
        self.nodes    = context.canonical_nodes or []
        self.node_map : Dict[int, CanonicalNode] = {n.id: n for n in self.nodes}
        self.comps    = sorted(self.graph.components, key=lambda c: c.edge_count, reverse=True)
        self.n_comps  = len(self.comps)
        self.sel_idx  = 0      # currently selected component (-1 = all)
        self.show_all = True

        # Toggle state
        self.show_geo   = True
        self.show_topo  = True
        self.show_bbox  = True
        self.show_nodes = True
        self.show_labels= True

        # Artist handles for fast redraw
        self._geo_artists   = []
        self._topo_artists  = []
        self._bbox_artists  = []
        self._node_artists  = []
        self._label_artists = []
        self._info_text     = None

        self._build()

    # ── Layout ────────────────────────────────────────────────────────────
    def _build(self):
        self.fig = plt.figure(figsize=(18, 11), facecolor=BG_COLOR)
        self.fig.canvas.manager.set_window_title("CAD Geometry Engine — 2D Engineering Debugger")

        # Main drawing area
        self.ax = self.fig.add_axes([0.22, 0.12, 0.76, 0.84], facecolor=BG_COLOR)
        self.ax.set_aspect("equal")
        self.ax.tick_params(colors="#444444", labelsize=7)
        for spine in self.ax.spines.values():
            spine.set_edgecolor("#333333")

        # Sidebar
        side_ax = self.fig.add_axes([0.0, 0.0, 0.22, 1.0], facecolor="#111111")
        side_ax.axis("off")

        # Title
        self.fig.text(0.01, 0.97, "Engineering Debugger",
                      color="white", fontsize=11, fontweight="bold", va="top")
        self.fig.text(0.01, 0.94, os.path.basename(self.context.filepath),
                      color="#888888", fontsize=8, va="top")

        # ── Stats block ──────────────────────────────────────────────────
        stats = (
            f"Canonical Nodes:  {len(self.nodes)}\n"
            f"Graph Edges:      {len(self.graph.edges)}\n"
            f"Components:       {self.n_comps}\n"
            f"Avg Degree:       {self.context.metrics.get('average_degree', 0)}\n"
            f"Largest Comp:     {self.context.metrics.get('largest_component', 0)} edges\n"
            f"\nBenchmarks:"
        )
        for ev in self.context.events:
            stats += f"\n  {ev.phase:<16} {ev.duration:.4f}s"
        self.fig.text(0.01, 0.91, stats, color=TEXT_COLOR,
                      fontsize=7.5, fontfamily="monospace", va="top")

        # ── Info panel (per selected component) ─────────────────────────
        self._info_text = self.fig.text(0.01, 0.53, "",
                                        color="#FFD700", fontsize=8,
                                        fontfamily="monospace", va="top",
                                        wrap=True)

        # ── Navigation buttons ────────────────────────────────────────────
        ax_prev = self.fig.add_axes([0.01, 0.20, 0.09, 0.04])
        ax_next = self.fig.add_axes([0.12, 0.20, 0.09, 0.04])
        ax_all  = self.fig.add_axes([0.01, 0.15, 0.20, 0.04])

        self.btn_prev = Button(ax_prev, "◄ Prev", color="#222233", hovercolor="#444455")
        self.btn_next = Button(ax_next, "Next ►", color="#222233", hovercolor="#444455")
        self.btn_all  = Button(ax_all,  "Show All Components", color="#223322", hovercolor="#446644")

        for b in [self.btn_prev, self.btn_next, self.btn_all]:
            b.label.set_color("white")
            b.label.set_fontsize(8)

        self.btn_prev.on_clicked(self._on_prev)
        self.btn_next.on_clicked(self._on_next)
        self.btn_all.on_clicked(self._on_show_all)

        # ── Toggle checkboxes ────────────────────────────────────────────
        ax_checks = self.fig.add_axes([0.005, 0.32, 0.21, 0.20], facecolor="#111111")
        labels  = ["DXF Geometry", "Topology Graph", "Bounding Boxes",
                   "Node Degrees", "Labels"]
        actives = [self.show_geo, self.show_topo, self.show_bbox,
                   self.show_nodes, self.show_labels]
        self.checks = CheckButtons(ax_checks, labels, actives)
        self.checks.on_clicked(self._on_toggle)
        for text in self.checks.labels:
            text.set_color(TEXT_COLOR)
            text.set_fontsize(8)

        # ── Legend ───────────────────────────────────────────────────────
        legend_elements = [
            Line2D([0], [0], color=DEGREE_COLORS[1],    marker="o", ms=6, lw=0, label="Degree 1 – endpoint"),
            Line2D([0], [0], color=DEGREE_COLORS[2],    marker="o", ms=6, lw=0, label="Degree 2 – chain"),
            Line2D([0], [0], color=DEGREE_DEFAULT,      marker="o", ms=6, lw=0, label="Degree 3+ – intersection"),
            Line2D([0], [0], color=SEL_COLOR,           lw=2,               label="Selected component"),
            Line2D([0], [0], color=UNSEL_COLOR,         lw=1, alpha=0.6,     label="Other components"),
            Line2D([0], [0], color=GEO_COLOR,           lw=1,               label="DXF raw geometry"),
        ]
        self.ax.legend(handles=legend_elements, loc="upper right",
                       fontsize=7, facecolor="#1a1a1a", edgecolor="#444",
                       labelcolor="white", framealpha=0.9)

        # ── Draw and bind keyboard ────────────────────────────────────────
        self._draw_all()
        self._fit_view()
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)

        plt.show()

    # ── Drawing helpers ───────────────────────────────────────────────────
    def _clear_artists(self, artist_list):
        for a in artist_list:
            try:
                a.remove()
            except Exception:
                pass
        artist_list.clear()

    def _draw_raw_geometry(self):
        self._clear_artists(self._geo_artists)
        if not self.show_geo:
            return

        for line in self.repo.lines.values():
            ln, = self.ax.plot(
                [line.start.x, line.end.x],
                [line.start.y, line.end.y],
                color=GEO_COLOR, lw=0.5, alpha=0.5, solid_capstyle="round"
            )
            self._geo_artists.append(ln)

        for arc in self.repo.arcs.values():
            ang1 = arc.start_angle
            ang2 = arc.end_angle
            if ang2 < ang1:
                ang2 += 360
            angles = np.linspace(math.radians(ang1), math.radians(ang2), 40)
            xs = arc.center.x + arc.radius * np.cos(angles)
            ys = arc.center.y + arc.radius * np.sin(angles)
            ln, = self.ax.plot(xs, ys, color=GEO_COLOR, lw=0.5, alpha=0.5)
            self._geo_artists.append(ln)

        for poly in self.repo.polylines.values():
            if len(poly.vertices) < 2:
                continue
            xs = [v.x for v in poly.vertices]
            ys = [v.y for v in poly.vertices]
            if poly.is_closed:
                xs.append(xs[0])
                ys.append(ys[0])
            ln, = self.ax.plot(xs, ys, color=GEO_COLOR, lw=0.5, alpha=0.5)
            self._geo_artists.append(ln)

    def _draw_topology(self):
        self._clear_artists(self._topo_artists)
        if not self.show_topo:
            return

        selected_comp = None if self.show_all else self.comps[self.sel_idx]
        selected_edges = set()
        if selected_comp:
            selected_edges = {id(e) for e in selected_comp.edges}

        for comp in self.comps:
            is_sel = (selected_comp is None or comp is selected_comp)
            color  = SEL_COLOR if (selected_comp and comp is selected_comp) else UNSEL_COLOR
            alpha  = 0.95 if is_sel else 0.25
            lw     = 1.6  if is_sel else 0.7

            for edge in comp.edges:
                n1 = self.node_map.get(edge.start_node)
                n2 = self.node_map.get(edge.end_node)
                if not n1 or not n2:
                    continue
                ln, = self.ax.plot(
                    [n1.point.x, n2.point.x],
                    [n1.point.y, n2.point.y],
                    color=color, lw=lw, alpha=alpha,
                    solid_capstyle="round"
                )
                self._topo_artists.append(ln)

    def _draw_bboxes(self):
        self._clear_artists(self._bbox_artists)
        if not self.show_bbox:
            return

        target_comps = [self.comps[self.sel_idx]] if not self.show_all else self.comps
        for comp in target_comps:
            x0, y0, x1, y1 = _comp_bbox(comp, self.node_map)
            if x1 == x0 and y1 == y0:
                continue
            pad = max((x1 - x0), (y1 - y0)) * 0.05 + 10
            rect = patches.Rectangle(
                (x0 - pad, y0 - pad),
                (x1 - x0 + 2 * pad), (y1 - y0 + 2 * pad),
                linewidth=1, edgecolor=BBOX_COLOR,
                facecolor="none", alpha=0.7, linestyle="--"
            )
            self.ax.add_patch(rect)
            self._bbox_artists.append(rect)

    def _draw_nodes(self):
        self._clear_artists(self._node_artists)
        if not self.show_nodes:
            return

        target_comps = [self.comps[self.sel_idx]] if not self.show_all else self.comps
        visited = set()
        for comp in target_comps:
            for nid in comp.nodes:
                if nid in visited:
                    continue
                visited.add(nid)
                node = self.node_map.get(nid)
                if not node:
                    continue
                deg = self.graph.node_degrees.get(nid, 0)
                color = DEGREE_COLORS.get(deg, DEGREE_DEFAULT)
                size  = 25 if deg == 1 else (15 if deg == 2 else 30)
                sc = self.ax.scatter(
                    node.point.x, node.point.y,
                    c=color, s=size, zorder=5, alpha=0.9,
                    linewidths=0
                )
                self._node_artists.append(sc)

    def _draw_labels(self):
        self._clear_artists(self._label_artists)
        if not self.show_labels:
            return

        target_comps = [self.comps[self.sel_idx]] if not self.show_all else self.comps[:50]
        for comp in target_comps:
            x0, y0, x1, y1 = _comp_bbox(comp, self.node_map)
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            is_sel = (not self.show_all)
            label = (
                f"C{comp.id}\n{comp.edge_count}e / {comp.node_count}n"
                if is_sel else
                f"C{comp.id}"
            )
            txt = self.ax.text(
                cx, cy, label,
                color=SEL_COLOR if is_sel else "#AAAAAA",
                fontsize=6, ha="center", va="center",
                fontfamily="monospace", alpha=0.85, zorder=6
            )
            self._label_artists.append(txt)

    def _update_info(self):
        if not self._info_text:
            return
        if self.show_all:
            self._info_text.set_text(
                f"Showing ALL {self.n_comps} components\n"
                f"\nPress N/P to navigate\nPress B for bounding boxes\n"
                f"Press D for node degrees"
            )
        else:
            comp = self.comps[self.sel_idx]
            total_len = _comp_length(comp)
            x0, y0, x1, y1 = _comp_bbox(comp, self.node_map)
            degrees = [self.graph.node_degrees.get(nid, 0) for nid in comp.nodes]
            deg_str = ", ".join(sorted(set(str(d) for d in degrees)))
            self._info_text.set_text(
                f"─── Component {self.sel_idx + 1}/{self.n_comps} ───\n"
                f"\n  ID       : {comp.id}"
                f"\n  Edges    : {comp.edge_count}"
                f"\n  Nodes    : {comp.node_count}"
                f"\n  Length   : {total_len:.1f}"
                f"\n  W × H    : {(x1-x0):.0f} × {(y1-y0):.0f}"
                f"\n  Degrees  : {deg_str}"
                f"\n  Recognizer: —"
                f"\n  Confidence: —"
                f"\n"
                f"\n[N] Next  [P] Prev  [A] All"
            )

    def _draw_all(self):
        self._draw_raw_geometry()
        self._draw_topology()
        self._draw_bboxes()
        self._draw_nodes()
        self._draw_labels()
        self._update_info()
        self.fig.canvas.draw_idle()

    def _fit_view(self, comp: Optional[ConnectedComponent] = None):
        if comp:
            x0, y0, x1, y1 = _comp_bbox(comp, self.node_map)
            pad = max((x1 - x0), (y1 - y0)) * 0.25 + 50
            self.ax.set_xlim(x0 - pad, x1 + pad)
            self.ax.set_ylim(y0 - pad, y1 + pad)
        else:
            # Fit all geometry
            all_x = [n.point.x for n in self.nodes]
            all_y = [n.point.y for n in self.nodes]
            if not all_x:
                return
            px = (max(all_x) - min(all_x)) * 0.05
            py = (max(all_y) - min(all_y)) * 0.05
            self.ax.set_xlim(min(all_x) - px, max(all_x) + px)
            self.ax.set_ylim(min(all_y) - py, max(all_y) + py)
        self.fig.canvas.draw_idle()

    # ── Event handlers ────────────────────────────────────────────────────
    def _on_prev(self, event):
        self.show_all = False
        self.sel_idx = (self.sel_idx - 1) % self.n_comps
        self._draw_all()
        self._fit_view(self.comps[self.sel_idx])

    def _on_next(self, event):
        self.show_all = False
        self.sel_idx = (self.sel_idx + 1) % self.n_comps
        self._draw_all()
        self._fit_view(self.comps[self.sel_idx])

    def _on_show_all(self, event):
        self.show_all = True
        self._draw_all()
        self._fit_view()

    def _on_toggle(self, label):
        if label == "DXF Geometry":     self.show_geo    = not self.show_geo
        elif label == "Topology Graph": self.show_topo   = not self.show_topo
        elif label == "Bounding Boxes": self.show_bbox   = not self.show_bbox
        elif label == "Node Degrees":   self.show_nodes  = not self.show_nodes
        elif label == "Labels":         self.show_labels = not self.show_labels
        self._draw_all()

    def _on_key(self, event):
        if event.key in ("n", "right"):      self._on_next(None)
        elif event.key in ("p", "left"):     self._on_prev(None)
        elif event.key == "a":               self._on_show_all(None)
        elif event.key == "t":
            self.show_topo = not self.show_topo
            self._draw_all()
        elif event.key == "g":
            self.show_geo = not self.show_geo
            self._draw_all()
        elif event.key == "b":
            self.show_bbox = not self.show_bbox
            self._draw_all()
        elif event.key == "d":
            self.show_nodes = not self.show_nodes
            self._draw_all()
        elif event.key == "l":
            self.show_labels = not self.show_labels
            self._draw_all()
        elif event.key == "r":
            self._fit_view()


# ─── Entry point ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="2D Engineering Debugger for the CAD Geometry Engine")
    parser.add_argument("drawing", help="Path to DXF file")
    args = parser.parse_args()

    engine = GeometryEngine()
    print(f"Loading {args.drawing}…")
    context = engine.load(args.drawing)
    context = engine.process(context)

    print("\n--- Pipeline Benchmarks ---")
    total = 0.0
    for ev in context.events:
        print(f"  {ev.phase:<20} {ev.duration:.4f} s")
        total += ev.duration
    print(f"  {'Total':<20} {total:.4f} s")
    print(f"\n  Components: {context.metrics.get('connected_components', 0)}")
    print(f"  Edges: {context.metrics.get('graph_edges', 0)}")

    DebugViewer(context)


if __name__ == "__main__":
    main()
