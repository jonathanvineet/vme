"""
run_phase6.py — Phase 6: Connectivity Graph Builder

Usage:
    python run_phase6.py <directory> [--golden]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm

from core.project import DrawingProject
from core.readers.dxf_reader import DXFReader
from core.geometry.canonicalizer import canonicalize
from core.spatial.engine import SpatialQueryEngine
from core.topology.node_builder import build_nodes
from core.topology.builder import TopologyBuilder

class GraphEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if hasattr(obj, '__dataclass_fields__'):
            return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

def _jdump(path: str, data: any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, cls=GraphEncoder)

def render_degree_overlay(graph, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 12))
    ax.set_facecolor('#0d0d1a')
    ax.set_title("Degree Overlay (Red=1, Green=2, Blue=3+)")
    
    xs1, ys1 = [], []
    xs2, ys2 = [], []
    xs3, ys3 = [], []
    
    for n in graph.nodes.values():
        if n.incident_edges == 1:
            xs1.append(n.position[0])
            ys1.append(n.position[1])
        elif n.incident_edges == 2:
            xs2.append(n.position[0])
            ys2.append(n.position[1])
        elif n.incident_edges >= 3:
            xs3.append(n.position[0])
            ys3.append(n.position[1])
            
    ax.plot(xs1, ys1, 'r.', markersize=2, label="Degree 1")
    ax.plot(xs2, ys2, 'g.', markersize=2, label="Degree 2")
    ax.plot(xs3, ys3, 'b.', markersize=2, label="Degree 3+")
    
    # Draw edges faint white
    for e in graph.edges.values():
        n1 = graph.nodes[e.start_node_uuid]
        n2 = graph.nodes[e.end_node_uuid]
        ax.plot([n1.position[0], n2.position[0]], [n1.position[1], n2.position[1]], color='w', lw=0.2, alpha=0.3)

    ax.legend()
    ax.set_aspect('equal', adjustable='datalim')
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, facecolor='#0d0d1a')
    plt.close()

def render_component_overlay(graph, comp_repo, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 12))
    ax.set_facecolor('#0d0d1a')
    ax.set_title("Connected Components Overlay")
    
    comps = list(comp_repo.components.values())
    colors = matplotlib.colormaps.get_cmap('hsv').resampled(len(comps)) if len(comps) > 0 else None
    
    for i, comp in enumerate(comps):
        c = colors(i) if colors else 'w'
        for e_id in comp.edge_ids:
            e = graph.edges[e_id]
            n1 = graph.nodes[e.start_node_uuid]
            n2 = graph.nodes[e.end_node_uuid]
            ax.plot([n1.position[0], n2.position[0]], [n1.position[1], n2.position[1]], color=c, lw=0.5, alpha=0.8)

    ax.set_aspect('equal', adjustable='datalim')
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, facecolor='#0d0d1a')
    plt.close()

def run_phase6(directory: str, write_golden: bool = False):
    project = DrawingProject()
    manifest = project.load_directory(directory)

    reader = DXFReader()
    
    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of or not drawing.capabilities.geometry:
            continue

        print(f"\n{'='*60}")
        print(f"PHASE 6: CONNECTIVITY GRAPH BUILDER | {filename}")
        print(f"{'='*60}")

        phase2_repo = reader.read_geometry(drawing.filepath, drawing.identity)
        canon_repo, val3 = canonicalize(phase2_repo, drawing.filepath)
        engine = SpatialQueryEngine.build(canon_repo)
        node_repo, val5, _ = build_nodes(canon_repo, engine, filename)
        
        builder = TopologyBuilder(node_repo, canon_repo)
        graph, comp_repo, metrics, validation = builder.build()
        
        print(f"Nodes Built                : {metrics['total_nodes']}")
        print(f"Edges Built                : {metrics['total_edges']}")
        print(f"Average Degree             : {metrics['average_degree']:.2f}")
        print(f"Connected Components       : {metrics['connected_components']}")
        print(f"Largest Component (nodes)  : {metrics['largest_component']}")
        
        crit_errs = len(validation["critical_errors"])
        warns = len(validation["warnings"])
        
        print("\nValidation Checks:")
        print(f"  Critical Errors          : {crit_errs}")
        print(f"  Warnings                 : {warns}")
        if crit_errs > 0:
            for e in validation["critical_errors"][:5]:
                print(f"    - {e}")

        ready = crit_errs == 0
        print(f"\nREADY FOR PHASE 7          : {'YES ✅' if ready else 'NO ❌'}")

        out_dir = os.path.join("debug", "phase06", filename)
        
        _jdump(os.path.join(out_dir, "graph.json"), {
            "nodes": {str(k): asdict(v) for k, v in graph.nodes.items()},
            "edges": {str(k): asdict(v) for k, v in graph.edges.items()},
            "node_to_edges": {str(k): [str(u) for u in v] for k, v in graph.node_to_edges.items()}
        })
        _jdump(os.path.join(out_dir, "components.json"), {str(k): asdict(v) for k, v in comp_repo.components.items()})
        _jdump(os.path.join(out_dir, "metrics.json"), metrics)
        _jdump(os.path.join(out_dir, "validation.json"), validation)
        
        render_degree_overlay(graph, os.path.join(out_dir, "degree_overlay.png"))
        render_component_overlay(graph, comp_repo, os.path.join(out_dir, "component_overlay.png"))
        
        print(f"  Debug outputs written to {out_dir}")
        
        if write_golden:
            golden_dir = os.path.join("tests", "golden", filename.replace(".dxf","").replace(".dwg",""), "phase06")
            os.makedirs(golden_dir, exist_ok=True)
            _jdump(os.path.join(golden_dir, "metrics.json"), metrics)
            _jdump(os.path.join(golden_dir, "components.json"), {str(k): asdict(v) for k, v in comp_repo.components.items()})
            print(f"  Golden corpus written to {golden_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--golden", action="store_true")
    args = parser.parse_args()
    run_phase6(args.directory, args.golden)
