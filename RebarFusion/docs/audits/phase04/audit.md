# Audit — Phase 4: Spatial Query Engine

## Scope
`core/spatial/engine.py` (`SpatialQueryEngine`), `core/spatial/indexes.py` (`PointIndex`, `BBoxIndex`, `OrientationIndex`, `SemanticIndex`, `LengthIndex`). Exercised by `run_phase4.py` against the Phase 3 canonical repository of `SS-GF-01(M).dxf`.

## Results

| Query method | Correctness | Runtime (ms) |
|---|---|---|
| nearest_point | PASS | 0.48 |
| within_radius | PASS | 3.34 |
| intersect_bbox | PASS | 0.99 |
| query_layer | PASS | 0.057 |
| query_type | PASS | 0.24 |
| query_orientation | PASS | 0.16 |
| parallel | PASS | 0.15 |
| similar_length | PASS | 0.0055 |
| text_near | PASS | 0.53 |
| dimension_near | PASS | 1.03 |
| fingerprint_lookup | PASS | 0.0013 |

All 11 acceptance checks pass (`acceptance_report.json`: all `true`). All queries run sub-millisecond to low-millisecond — no performance concern at this corpus size (1877 canonical entities). Debug artifacts present: `benchmarks.json`, `acceptance_report.json`, `bbox_index.json`, `point_index.json`, `orientation_index.json`, `layer_index.json`.

## Gap found
**No regression protection.** `tests/regression.py` builds the spatial engine only as a dependency for later phase checks (Phase 5/6) — it never asserts anything about Phase 4's own acceptance results or benchmarks. A `tests/golden/SS-GF-01(M)/phase04/benchmarks.json` golden file exists but is never read back by any test. A comment in `run_phase3.py` explicitly rationalizes this: *"Phase 4 (stub for completeness, benchmarks normally aren't regressed strictly)"* — reasonable for timing (benchmarks are environment-dependent), but the **correctness** acceptance checks (the 11 PASS/FAIL results, not the timings) have no reason to be excluded from regression and currently aren't checked at all.

## Verdict: **PASS functionally, untested going forward**
All correctness checks pass today. Because this phase has zero regression coverage, a future refactor of any spatial index could silently break query correctness with no test failure anywhere in the suite.

## Recommendation
Split the golden file into `acceptance.json` (hard regression check — these are deterministic, not timing-dependent) and `benchmarks.json` (informational only, as today).
