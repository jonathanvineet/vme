import json
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parent
DWG_PATH = ROOT / "DRAWINGS" / "SS-GF-01(M).dxf"
OUT_PATH = ROOT / "inspect_blocks.json"


doc = ezdxf.readfile(str(DWG_PATH))
msp = doc.modelspace()

blocks = Counter()
block_entities = defaultdict(Counter)
block_details = {}

print("=" * 80)
print("INSERTS ON S-RBAR")
print("=" * 80)

for e in msp:
    if e.dxf.layer != "S-RBAR":
        continue

    if e.dxftype() != "INSERT":
        continue

    name = e.dxf.name
    blocks[name] += 1

for name, count in blocks.most_common():
    print(f"{count:5d}  {name}")

for name in blocks:
    if name not in doc.blocks:
        continue

    block = doc.blocks[name]
    counts = Counter()
    entities = []

    for ent in block:
        typ = ent.dxftype()
        counts[typ] += 1
        entities.append(typ)
        block_entities[name][typ] += 1

    block_details[name] = {
        "count": blocks[name],
        "entity_counts": dict(counts),
        "entity_types": entities,
    }

payload = {
    "dwg": str(DWG_PATH),
    "insert_counts": blocks.most_common(),
    "block_details": block_details,
    "block_entity_breakdown": {
        name: dict(counter) for name, counter in block_entities.items()
    },
}

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)

print(f"\nWrote JSON summary to: {OUT_PATH}")
