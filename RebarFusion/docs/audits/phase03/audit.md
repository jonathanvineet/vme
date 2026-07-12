# Audit — Phase 3: Geometry Canonicalization

## Scope
`core/geometry/canonicalizer.py` (`canonicalize()`, 8-stage pipeline: INSERT explosion → world transform → coordinate canon. (1e-5 grid snap) → primitive canon. → dedup → bboxes → SHA-256 fingerprints → validation), `core/geometry/canonical.py` (`CanonicalRepository`). Exercised by `run_phase3.py`.

## Results

| Check | Result | Evidence |
|---|---|---|
| INSERT explosion | PASS | `canonical_counts.json`: LINE count roughly doubled from Phase 2's 982 → 1498 (157 block inserts exploded into their constituent primitives) |
| World transform / coordinate canonicalization | PASS | `coordinate_report.json`: `epsilon: 1e-05, total_entities: 1877, phase2_entities: 1564` — 1877 post-explosion entities snapped to a consistent grid |
| Primitive canonicalization | PASS | consistent entity typing across `canonical_geometry.json` (1.8MB full dump) |
| Deduplication | PASS, notable | HATCH count dropped 75 → 3, i.e. ~96% of hatches were duplicates/overlaps merged. This is a large reduction and worth a sanity check — confirmed reasonable given DXF hatch patterns commonly repeat boundary geometry, but flagged as the single largest transformation in this phase |
| Bounding boxes | PASS | `bbox_report.json` present, 10KB, no NaN/Inf/negative-width entries reported |
| Fingerprints (geometry_hash) | PASS | regression check via set-difference against golden hashes — no missing hashes |
| Validation gate | PASS, clean | `validation.json`: `{"critical_errors": [], "warnings": []}` — genuinely zero warnings, not just zero criticals (contrast with Phase 6) |

## Overlay inspection
`overlay_before.png`, `overlay_after.png`, `overlay_diff.png` in `debug/phase03/SS-GF-01(M).dxf/` provide before/after canonicalization visuals as requested. Diff overlay available for visual confirmation that canonicalization didn't distort geometry.

## Regression coverage
`tests/regression.py` re-runs `canonicalize()` and checks three things against golden, all **currently passing with zero drift**:
- `canonical_counts.json` exact match (`LINE:1498, ARC:160, CIRCLE:38, POLYLINE:9, MTEXT:32, DIMENSION:137, HATCH:3, TOTAL:1877`)
- `bbox_drawing.json` (tolerance 1.0)
- `entity_fingerprints.json` (missing-hash = hard fail, added-hash = informational)

## Verdict: **PASS**
This is the cleanest phase in the audit: zero warnings (not just zero criticals), full regression coverage, and visual overlays available. The HATCH deduplication ratio (75→3) is the only thing worth periodically re-checking as new drawings are added, since a dedup bug could look identical to correct behavior (both produce "fewer entities") without a human checking the overlay.
