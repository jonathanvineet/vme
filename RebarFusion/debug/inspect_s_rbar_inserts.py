import json
from collections import Counter
from pathlib import Path

import ezdxf
from ezdxf import bbox as ezbbox


def vec3_to_list(value):
    if value is None:
        return None
    try:
        return [float(value.x), float(value.y), float(getattr(value, "z", 0.0))]
    except AttributeError:
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except Exception:
            return [float(value[0]), float(value[1])]


def bbox_to_list(value):
    if value is None:
        return None
    min_pt, max_pt = value
    return [vec3_to_list(min_pt), vec3_to_list(max_pt)]


ROOT = Path(__file__).resolve().parent
DWG_PATH = (ROOT / ".." / "DRAWINGS" / "SS-GF-01(M).dxf").resolve()
OUT_PATH = ROOT / "inspect_s_rbar_inserts.json"


doc = ezdxf.readfile(str(DWG_PATH))
msp = doc.modelspace()

records = []
name_counts = Counter()

for entity in msp:
    if entity.dxftype() != "INSERT":
        continue
    if entity.dxf.layer != "S-RBAR":
        continue

    name = entity.dxf.name
    insert_point = vec3_to_list(entity.dxf.insert)
    rotation = float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
    xscale = float(getattr(entity.dxf, "xscale", 1.0) or 1.0)
    yscale = float(getattr(entity.dxf, "yscale", 1.0) or 1.0)
    zscale = float(getattr(entity.dxf, "zscale", 1.0) or 1.0)

    name_counts[name] += 1

    block = doc.blocks.get(name)
    block_entity_counts = Counter()
    block_bbox = None
    transformed_bbox = None

    if block is not None:
        for block_entity in block:
            block_entity_counts[block_entity.dxftype()] += 1

        try:
            block_bbox = ezbbox.extents(block)
            transformed_entities = list(entity.virtual_entities())
            transformed_bbox = ezbbox.extents(transformed_entities)
        except Exception:
            transformed_bbox = None

    records.append(
        {
            "name": name,
            "insert": insert_point,
            "rotation": rotation,
            "xscale": xscale,
            "yscale": yscale,
            "zscale": zscale,
            "layer": entity.dxf.layer,
            "block_entity_counts": dict(block_entity_counts),
            "block_bbox": bbox_to_list(block_bbox),
            "transformed_bbox": bbox_to_list(transformed_bbox),
        }
    )

summary = {
    "dwg": str(DWG_PATH),
    "insert_count": len(records),
    "name_counts": dict(name_counts),
    "records": records,
}

with open(OUT_PATH, "w", encoding="utf-8") as handle:
    json.dump(summary, handle, indent=2)

print("=" * 80)
print("S-RBAR INSERT TRANSFORMS")
print("=" * 80)
print(f"DWG: {DWG_PATH}")
print(f"INSERT count: {len(records)}")
print()

for record in records:
    print("-" * 80)
    print("NAME:", record["name"])
    print("INSERT:", record["insert"])
    print("ROTATION:", record["rotation"])
    print("XSCALE:", record["xscale"])
    print("YSCALE:", record["yscale"])
    print("ZSCALE:", record["zscale"])
    print("LAYER:", record["layer"])
    print("BLOCK ENTITY COUNTS:", record["block_entity_counts"])
    print("BLOCK BBOX:", record["block_bbox"])
    print("TRANSFORMED BBOX:", record["transformed_bbox"])

print()
print("Wrote JSON summary to:", OUT_PATH)
