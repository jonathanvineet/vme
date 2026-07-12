# Audit — Phase 2: Geometry Translation (DXF → Repository)

## Scope
`core/readers/dxf_reader.py` (`DXFReader.read_geometry()`), `core/geometry/repository.py`, `core/geometry/entities.py`. Exercised by `run_phase2.py` (production path) and `run_phase2_audit.py` (5-part trust audit), both against `test_project/SS-GF-01(M).dxf` — the only drawing with a registered reader.

## Audit results (from re-running `run_phase2_audit.py` live, since results are not persisted)

| Audit | Result | Detail |
|---|---|---|
| 1. Entity Conservation | PASS | raw DXF entity count == repository entity count (accounting for UNKNOWN types) |
| 2. Geometry Fidelity | PASS (visual) | Overlay of 50 lines, 20 arcs, 20 inserts, 20 dimensions saved to `debug/phase02_audit/fidelity_overlay.png` — pass is asserted by the script but genuinely requires **visual human confirmation**, which this audit performed by inspecting the render |
| 3. Bounding Box Validation | PASS | 1564/1564 entities have valid bboxes; 0 zero-fallback, 0 invalid |
| 4. UUID Stability | PASS | Same file read twice → identical UUID (`029e28b3-f1de-5b3a-b6fd-2342da68b5a2` both runs) |
| 5. Provenance Integrity | PASS | Sampled LINE/ARC/INSERT/DIMENSION entities all carry `handle, layer, color, linetype, owner_handle, parent_block, raw_properties` |

Script prints **"PHASE 2 FROZEN — Repository is trustworthy."**

## Overlay inspection
`debug/phase02_audit/fidelity_overlay.png` (~70KB) shows original DXF geometry against repository-translated geometry for the sampled entities; no visible divergence in the sampled set. Note: this is a **sample overlay** (50 lines / 20 arcs / 20 inserts / 20 dimensions out of 1564 entities), not a full pixel-perfect comparison of every entity as the audit brief originally called for — it is a reasonable proxy but not exhaustive.

## Regression coverage
`tests/regression.py` independently re-derives Phase 2 output and diffs entity-type counts against `tests/golden/SS-GF-01(M)/phase02/translation_report.json`. **Currently passing**, exact match: `LINE:982, ARC:134, POLYLINE:9, INSERT:157, TEXT:0, MTEXT:32, DIMENSION:137, HATCH:75, CIRCLE:38, UNKNOWN:0`.

## Gap found
`run_phase2_audit.py` writes only one artifact (`fidelity_overlay.png`) to disk — the PASS/FAIL verdicts for all 5 audits exist **only as stdout**, never serialized to JSON. If this script isn't re-run, there is no artifact proving Phase 2 was ever audited. This audit had to re-execute the script live to get evidence.

## Verdict: **PASS**
All 5 audits pass, both live and via regression. This is the best-verified phase in the pipeline. Only meaningful risk: the audit script's non-persistence (fix recommended in architecture_review.md §7) and the fact it only covers one drawing.
