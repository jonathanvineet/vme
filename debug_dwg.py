from collections import Counter, defaultdict
from pathlib import Path

import ezdxf


ROOT = Path(__file__).resolve().parent
DWG_PATH = ROOT / "DRAWINGS" / "SS-GF-01(M).dxf"


doc = ezdxf.readfile(str(DWG_PATH))
msp = doc.modelspace()

entity_counts = Counter()
layer_counts = Counter()
layer_entity = defaultdict(Counter)

print("=" * 80)
print("ENTITY SUMMARY")
print("=" * 80)

for e in msp:
    typ = e.dxftype()
    layer = e.dxf.layer

    entity_counts[typ] += 1
    layer_counts[layer] += 1
    layer_entity[layer][typ] += 1

print("\nEntity Types\n")

for t, c in entity_counts.most_common():
    print(f"{t:20} {c}")

print("\n\nLayers\n")

for l, c in layer_counts.most_common():
    print(f"{l:20} {c}")

print("\n\nLayer Breakdown\n")

for layer in sorted(layer_entity):
    print("\n" + "=" * 60)
    print(layer)
    print("=" * 60)

    for t, c in layer_entity[layer].most_common():
        print(f"{t:20} {c}")
