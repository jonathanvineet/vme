# Rebar Extractor

Extract rebars from CAD drawings (DXF, vector PDF). The project extracts linear entities, merges connected segments, computes geometry, detects neighbouring parallel rebars, and exports CSV/JSON and an annotated image.

Requirements
- Python 3.11
- See `requirements.txt` for pip install

Install

```bash
python -m pip install -r rebar_extractor/requirements.txt
```

Usage

```bash
python -m rebar_extractor.main path/to/drawing.dxf --out-csv out.csv --out-json out.json --out-image preview.png
```

Notes
- DWG reading is not implemented unless Aspose.CAD is available (commercial).
- The PDF reader extracts vector line drawing primitives via PyMuPDF and approximates arcs where needed.
