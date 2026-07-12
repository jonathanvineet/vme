# Phase 7.1 — Determinism Audit

## Symptom
Two consecutive, identical runs of the regression suite on the same drawing (`SS-GF-01(M).dxf`, no source changes) reported different recognition fingerprints for a small, varying number of components each time.

## Reproduction
Ran `RecognizerRegistry.evaluate()` over every connected component 10 times in one process, hashing the full label/fingerprint/measurements output each run:

```
run 1: 4772e2d7...
run 2: 87898fa9...
run 3: 5268a90b...
run 4: 8f80dc5c...
run 5: 5268a90b...
...
unique hashes: 4 / 10
```

Diffing run 1 against the others showed the recognized **label never changed** (e.g. `u_bar -> u_bar`) — only the `measurements` (and therefore the fingerprint hash of them) drifted, always in the last 1-2 significant digits of a float, e.g. `total_length: 1491.796986049268` vs `1491.7969860492683`.

## Root cause
Traced through the pipeline by pinning one drifting component and printing its `comp.edge_ids` order plus the underlying `canon_repo.lines`/`arcs` entity IDs across two runs. **The canonical entity UUIDs themselves were different values between runs** for the same logical entity (e.g. the geometrically-identical "first line" was `26e727b2-...` in one run and `643f72b4-...` in the next).

Traced further to `core/readers/dxf_reader.py:132`:
```python
DRAWING_NS = uuid.UUID(str(identity.uuid))
```
every canonical entity UUID is derived (via `uuid5`) from `identity.uuid`. That value comes from `core/identity_parser.py::parse_identity()`, which called `uuid.uuid4()` — **a fresh random UUID on every single `project.load_directory()` call**, in both code paths (matched-filename and fallback). So the same drawing, loaded twice, produced a completely different but internally-consistent set of entity UUIDs each time.

This is not a new discovery in isolation — `tests/regression.py` already carries a comment acknowledging it (*"UUIDs for exploded entities are derived from the drawing identity UUID which is re-generated each project load"*), which is why the Phase 3 fingerprint regression check deliberately compares `geometry_hash` values (position-derived, stable) instead of entity UUIDs. What hadn't been accounted for is that this randomness **propagates past entity identity into computation order**: `TopologyBuilder._stage_6_4_components` collects edges into a Python `set` (`comp_edges`) keyed by these (now-random) edge UUIDs, then converts to a list for component statistics. Python `set` iteration order for a fixed set of values is deterministic, but depends on the hash-table slot each value lands in, which — for UUIDs whose *values themselves* change between runs — differs every time. `_stage_6_6_metrics` then sums edge lengths in that list's order (`total_len += l`), and floating-point addition is not associative, so summing the same three float values in a different order produces a different last-bit result. That different float, once JSON-serialized into `measurements` and hashed for the fingerprint, produces a different fingerprint despite representing the same geometric quantity to 12+ significant digits.

Chain: `uuid.uuid4()` per load → random entity UUIDs → random edge UUIDs → random `set` iteration order → order-dependent float summation → different fingerprint hash.

## Fix
`core/identity_parser.py`: replaced both `uuid.uuid4()` calls with `uuid.uuid5(NAMESPACE_IDENTITY, filename)`, where `NAMESPACE_IDENTITY` is a fixed constant UUID (same pattern already used elsewhere in the codebase for `NAMESPACE_NODE`, `NAMESPACE_EDGE`, `NAMESPACE_COMPONENT`). The drawing identity — and everything derived from it — is now a pure function of the filename, not a per-process random value.

No other phase's code needed to change; entity ID *values* were never asserted against golden files anywhere (only counts, bboxes, and geometry hashes), so this fix doesn't disturb any existing "frozen" verification.

Checked for other `uuid.uuid4()` call sites that could reintroduce this class of bug:
- `core/topology/builder.py:140` — a temporary placeholder for `ConnectedComponent.id`, immediately overwritten by a deterministic `uuid5` (geometry-hash-derived) two lines later in `_stage_6_5_component_uuids`. Not a determinism risk.
- `core/project.py:96` — a session-level `project_uuid`, not consumed by any geometry/entity hashing path. Out of scope.
- `core/geometry/normalizer.py`, `core/engineering/solver.py`, `core/geometry/parser.py`, `core/engineering/association.py` — Phase 8/9 territory, not yet audited. Flagged for the next round, not fixed here (this round's scope was Phase 7 determinism only).

## Verification
- Re-ran the 10x hash check after the fix: **1 unique hash / 10 runs**. Re-ran again at 15x: **1 unique hash / 15 runs**.
- Added a permanent check, `tests/determinism.py <directory> [--runs N]`, that runs the pipeline through Phase 7 recognition N times (default 10) and fails if more than one distinct output hash appears. This is now part of the regression toolset going forward — run it any time topology or recognition code changes.
- Re-baselined `tests/golden/SS-GF-01(M)/phase07/recognition_results.json` — the old golden was captured under the nondeterministic regime and encoded one arbitrary float value for `total_length` on one component; the new golden reflects the now-stable, reproducible value. Confirmed via `tests/regression.py` that Phase 7 recognition now reports ✅ with zero drift, repeatably.
- Full regression suite (`tests/regression.py test_project`) now has exactly one remaining failure: the 4 still-unresolved `A-FLOR` duplicate-edge pairs from the Phase 6 audit (`audit_phase06_defect_classification.md`), correctly held open pending a domain call. Everything else — Phase 2, 3, 6 metrics/stability, and now Phase 7 recognition — passes cleanly and reproducibly.

## Verdict
Root cause fixed at the source (Phase 1 identity generation), not papered over downstream. Phase 7 recognition is now deterministic and regression-locked. Phases 8-10 remain unaudited and should not be assumed correct yet — this round's scope was explicitly limited to the determinism issue.
