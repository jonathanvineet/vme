import ezdxf

def inspect_annotations(filepath):
    try:
        doc = ezdxf.readfile(filepath)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return
        
    msp = doc.modelspace()

    for e in msp:
        if e.dxftype() == "MTEXT":
            print("="*80)
            print("MTEXT")
            print("Position:", e.dxf.insert)
            print(e.text)

        elif e.dxftype() == "TEXT":
            print("="*80)
            print("TEXT")
            print("Position:", e.dxf.insert)
            print(e.dxf.text)

        elif e.dxftype() == "DIMENSION":
            print("="*80)
            print("DIMENSION")
            print("Definition point:", getattr(e.dxf, "defpoint", None))
            print("Text midpoint:", getattr(e.dxf, "text_midpoint", None))
            print("Measurement:", getattr(e.dxf, "actual_measurement", None))

if __name__ == "__main__":
    inspect_annotations("../DRAWINGS/SS-GF-01(M).dxf")
