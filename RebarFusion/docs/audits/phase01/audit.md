# Audit — Phase 1: Project Loading / Drawing Manifest

## Scope
`core/project.py` (`DrawingProject.load_directory()`, `report_health()`), exercised by `run_phase1_tests.py` against `test_project/` (13 fixture files: 1 `.dxf`, 8 `.dwg`, 4 `.pdf`, including a deliberate exact-duplicate `.dwg` and a renamed duplicate `banana.dwg`).

## Checks performed and results

| Check | Result | Evidence |
|---|---|---|
| Project/drawing discovery | PASS | `manifest.json` lists all 13 fixture files |
| Metadata extraction (entity counts, bbox, layers) | PASS for `.dxf`, N/A for `.dwg`/`.pdf` | `statistics.json`: only `SS-GF-01(M).dxf` has non-empty `entity_counts` (982 LINE, 134 ARC, 75 HATCH, 38 CIRCLE, 157 INSERT, 9 POLYLINE, 32 MTEXT, 137 DIMENSION) and real bbox `[59547.9, 2512.9, 97855.9, 30497.6]`. `.dwg`/`.pdf` files all report empty counts / zero bbox because **no reader is registered for those extensions** |
| Duplicate detection | PASS | `duplicates.json`: `{"PW-GF-02(M1).dwg": "banana.dwg", "PW-GF-02(M1)-copy.dwg": "banana.dwg"}` — both byte-identical copies correctly flagged against the renamed original |
| Drawing identity parsing (number/view from filename) | PASS for convention-following names, expected fallback otherwise | `project_graph.json` groups drawings under `GF → PW/SS → PW-GF-02 / PW-GF-09 / SS-GF-01`; `banana.dwg` and `PW-GF-02(M1)-copy.dwg` fall into an `"Unknown"` bucket since they don't follow the naming convention — this is correct/expected behavior for those synthetic filenames, not a bug |
| Validation errors/warnings | PASS (no errors) | `validation.json`: zero `errors` for every file; only expected `"No reader available for extension: dwg"` / `"...pdf"` warnings; `SS-GF-01(M).dxf`, `PW-GF-02(M1).dwg`, `PW-GF-02(M1)-copy.dwg` have zero warnings |
| Checksum stability | NOT DIRECTLY TESTED — duplicate detection implies a checksum/hash comparison is working correctly (it caught byte-identical files), but there is no dedicated test that hashes the same file twice and asserts equality |

## Debug artifacts present
`debug/phase01/`: `manifest.json`, `statistics.json`, `validation.json`, `project_graph.json`, `duplicates.json`, `metadata.json`, `registration.json` — all dated 2026-07-05, i.e. **stale relative to later phases' debug output** (Phase 3–6 debug artifacts are dated 2026-07-06). Should be regenerated to confirm they still reflect current code.

## Test coverage
**None.** `run_phase1_tests.py` contains zero `assert` statements — it is a manual scenario/dump script, not a test. `tests/regression.py` does not cover Phase 1 at all (its first check is Phase 2). This is a gap: a future change to `DrawingProject`, `identity_parser.py`, or duplicate detection could silently break Phase 1 with no CI signal.

## Verdict: **PASS, but unguarded**
Functionally correct for the one scenario exercised. No regression protection exists. Given 12 of 13 fixture drawings never get past this phase (no DWG/PDF reader), Phase 1's "success" is really only proven for file discovery/dedup/identity-parsing logic, not for metadata extraction on non-DXF formats.

## Recommendation
Add a `tests/golden/.../phase01/` fixture and a Phase 1 check block to `tests/regression.py` (manifest entry count, duplicate map, project graph structure) so this phase gets the same protection as Phases 2/3/6.
