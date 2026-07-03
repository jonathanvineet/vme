import json
from collections import Counter
from core.parser import CADParser
from core.normalizer import Normalizer
from core.geometry import LineEntity, ArcEntity, PolylineEntity, TextEntity, DimensionEntity, BlockReference

def main():
    print("--- Phase 1: CAD Parser ---")
    parser = CADParser()
    filepath = "../DRAWINGS/SS-GF-01(M).dxf"
    print(f"Reading {filepath}...")
    entities = parser.parse_dxf(filepath)
    
    types_count = Counter([type(e).__name__ for e in entities])
    print("Parsed entities:")
    for t, c in types_count.items():
        print(f"  {t}: {c}")

    print("\n--- Phase 2: Geometry Normalization ---")
    normalizer = Normalizer()
    normalized_entities = normalizer.normalize(entities)
    
    norm_types_count = Counter([type(e).__name__ for e in normalized_entities])
    print("Normalized flat entities (after explode & dedup):")
    for t, c in norm_types_count.items():
        print(f"  {t}: {c}")

if __name__ == "__main__":
    main()
