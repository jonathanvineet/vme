import csv
import json
from collections import Counter
from math import hypot
from pathlib import Path

import ezdxf


ROOT = Path(__file__).resolve().parent
DWG_PATH = ROOT / "DRAWINGS" / "SS-GF-01(M).dxf"


doc = ezdxf.readfile(str(DWG_PATH))
msp = doc.modelspace()

print("=" * 80)
print("S-RBAR CONTENTS")
print("=" * 80)

lengths = []
type_counts = Counter()
insert_names = Counter()

with open(ROOT / "s_rbar_dump.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["type", "layer", "length", "x1", "y1", "x2", "y2"])

    for e in msp:
        if e.dxf.layer != "S-RBAR":
            continue

        type_counts[e.dxftype()] += 1

        if e.dxftype() == "INSERT":
            insert_names[e.dxf.name] += 1

        print("-" * 80)
        print(e.dxftype())

        if e.dxftype() == "LINE":
            x1, y1, _ = e.dxf.start
            x2, y2, _ = e.dxf.end

            L = hypot(x2 - x1, y2 - y1)
            lengths.append(round(L, 1))

            print("Length:", round(L, 2))
            print("Start :", round(x1, 1), round(y1, 1))
            print("End   :", round(x2, 1), round(y2, 1))

            w.writerow(["LINE", "S-RBAR", round(L, 2), x1, y1, x2, y2])

        elif e.dxftype() == "LWPOLYLINE":
            pts = list(e.get_points())
            print("Vertices:", len(pts))
            print("Closed:", e.closed)
            print("Points:")
            for p in pts:
                print(" ", p[:2])

        elif e.dxftype() == "INSERT":
            print("Block:", e.dxf.name)

        elif e.dxftype() == "TEXT":
            print(e.dxf.text)

        elif e.dxftype() == "MTEXT":
            print(e.text)

print("\n" + "=" * 80)
print("LINE LENGTH DISTRIBUTION")
print("=" * 80)
print(Counter(lengths).most_common(50))

print("\n" + "=" * 80)
print("S-RBAR TYPE COUNTS")
print("=" * 80)
print(type_counts)

print("\n" + "=" * 80)
print("INSERT NAME COUNTS")
print("=" * 80)
print(insert_names)

summary = {
    "dwg": str(DWG_PATH),
    "length_distribution": Counter(lengths).most_common(50),
    "type_counts": dict(type_counts),
    "insert_name_counts": dict(insert_names),
}

with open(ROOT / "inspect_s_rbar.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print("\nWrote JSON summary to:", ROOT / "inspect_s_rbar.json")
import csv
import json
from collections import Counter
from math import hypot
from pathlib import Path

import ezdxf


ROOT = Path(__file__).resolve().parent
DWG_PATH = ROOT / "DRAWINGS" / "SS-GF-01(M).dxf"


doc = ezdxf.readfile(str(DWG_PATH))
msp = doc.modelspace()

print("=" * 80)
print("S-RBAR CONTENTS")
print("=" * 80)

lengths = []

with open(ROOT / "s_rbar_dump.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["type", "layer", "length", "x1", "y1", "x2", "y2"])

    for e in msp:
        if e.dxf.layer != "S-RBAR":
            continue

        print("-" * 80)
        print(e.dxftype())

        if e.dxftype() == "LINE":

        print("\n" + "=" * 80)
        print("S-RBAR TYPE COUNTS")
        print("=" * 80)

        type_counts = Counter()
        insert_names = Counter()

        for e in msp:
            if e.dxf.layer != "S-RBAR":
                continue

            type_counts[e.dxftype()] += 1

            if e.dxftype() == "INSERT":
                insert_names[e.dxf.name] += 1

        print(type_counts)

        print("\n" + "=" * 80)
        print("INSERT NAME COUNTS")
        print("=" * 80)
        print(insert_names)

        summary = {
            "dwg": str(DWG_PATH),
            "length_distribution": Counter(lengths).most_common(50),
            "type_counts": dict(type_counts),
            "insert_name_counts": dict(insert_names),
        }

        with open(ROOT / "inspect_s_rbar.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        print("\nWrote JSON summary to:", ROOT / "inspect_s_rbar.json")
            x1, y1, _ = e.dxf.start
            x2, y2, _ = e.dxf.end

            L = hypot(x2 - x1, y2 - y1)
            lengths.append(round(L, 1))

            print("Length:", round(L, 2))
            print("Start :", round(x1, 1), round(y1, 1))
            print("End   :", round(x2, 1), round(y2, 1))

            w.writerow(["LINE", "S-RBAR", round(L, 2), x1, y1, x2, y2])

        elif e.dxftype() == "LWPOLYLINE":
            pts = list(e.get_points())
            print("Vertices:", len(pts))
            print("Closed:", e.closed)
            print("Points:")
            for p in pts:
                print(" ", p[:2])

        elif e.dxftype() == "INSERT":
            print("Block:", e.dxf.name)

        elif e.dxftype() == "TEXT":
            print(e.dxf.text)

        elif e.dxftype() == "MTEXT":
            print(e.text)

print("\n" + "=" * 80)
print("LINE LENGTH DISTRIBUTION")
print("=" * 80)
print(Counter(lengths).most_common(50))
