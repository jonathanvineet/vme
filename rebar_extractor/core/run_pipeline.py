import argparse
import json
import os
import uuid
from dataclasses import asdict
from core.engine import GeometryEngine

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if hasattr(obj, 'as_tuple'):
            return obj.as_tuple()
        if hasattr(obj, '__dataclass_fields__'):
            return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
        return super().default(obj)

def dump_snapshot(filename: str, data: list):
    os.makedirs("debug", exist_ok=True)
    filepath = os.path.join("debug", filename)
    with open(filepath, 'w') as f:
        serializable = []
        for e in data:
            if hasattr(e, '__dataclass_fields__'):
                d = asdict(e)
            else:
                d = e
            serializable.append(d)
        json.dump(serializable, f, indent=2, cls=UUIDEncoder)
    print(f"  Snapshot written to {filepath}")

def main():
    parser = argparse.ArgumentParser(description="Run CAD Geometry Engine Pipeline")
    parser.add_argument("drawing", help="Path to DXF/DWG file")
    parser.add_argument("--until", help="Run pipeline until this stage completes", default=None)
    parser.add_argument("--debug", action="store_true", help="Dump debug snapshots")
    args = parser.parse_args()

    engine = GeometryEngine()
    print(f"Loading {args.drawing}...")
    context = engine.load(args.drawing)
    
    print(f"Processing context (until={args.until})...")
    context = engine.process(context, until=args.until)
    
    print("\n--- Pipeline Benchmarks ---")
    total_time = 0.0
    for event in context.events:
        print(f"{event.phase.ljust(20)} {event.duration:.4f} s")
        total_time += event.duration
    print(f"{'Total'.ljust(20)} {total_time:.4f} s")
    
    # We could theoretically calculate peak memory here, but keeping it simple for now
    
    print("\n--- Graph Statistics ---")
    print(f"Canonical Nodes: {len(context.canonical_nodes) if context.canonical_nodes else 0}")
    print(f"Graph Edges: {context.metrics.get('graph_edges', 0)}")
    print(f"Connected Components: {context.metrics.get('connected_components', 0)}")
    print(f"Average Degree: {context.metrics.get('average_degree', 0)}")
    print(f"Largest Component: {context.metrics.get('largest_component', 0)} edges")

    print("\n--- Validation Warnings ---")
    for event in context.events:
        if event.warnings:
            print(f"[{event.phase}]")
            for w in event.warnings:
                print(f"  Warning: {w}")

    print("\n--- Shape Recognition ---")
    type_counts = context.metrics.get("recognition_type_counts", {})
    recognized_bars = context.metrics.get("recognized_bars", [])
    if type_counts:
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"  {t:<22} {c}")
        print(f"  {'─'*30}")
        print(f"  {'Bar candidates':<22} {len(recognized_bars)}")
    else:
        print("  (shape recognition not yet run)")

    if args.debug:
        if "parser" in context.metrics:
            dump_snapshot("01_parsed.json", context.metrics.get("_raw_parsed", []))
        if "normalizer" in context.metrics:
            dump_snapshot("02_normalized.json", context.repository.get_all())
            print("\n  Repository statistics:")
            print(f"    Lines: {len(context.repository.lines)}")
            print(f"    Arcs: {len(context.repository.arcs)}")
            print(f"    Polylines: {len(context.repository.polylines)}")
            print(f"    Texts: {len(context.repository.texts)}")
            print(f"    Dimensions: {len(context.repository.dimensions)}")
            print(f"    Blocks: {len(context.repository.blocks)}")
            print(f"    Total Entities: {len(context.repository.entities)}")

if __name__ == "__main__":
    main()
