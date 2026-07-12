# RebarFusion — Architecture Review (Step 1)

Date: 2026-07-11
Scope: full-repo read (docs, `core/`, `run_phaseN.py` scripts, `debug/`, `tests/`) prior to auditing Phases 1–6.

## 1. Pipeline as it actually exists

```
Phase 1  core/project.py            DrawingProject.load_directory()   → manifest, duplicates, project graph
Phase 2  core/readers/dxf_reader.py DXFReader.read_geometry()         → DrawingRepository (typed entities)
Phase 3  core/geometry/canonicalizer.py canonicalize()                → CanonicalRepository (8-stage pipeline)
Phase 4  core/spatial/engine.py     SpatialQueryEngine.build()        → spatial indexes + query API
Phase 5  core/topology/node_builder.py build_nodes()                  → CanonicalNodeRepository
Phase 6  core/topology/builder.py   TopologyBuilder.build()           → ConnectivityGraph + components
Phase 7  core/recognition/*         (recognizers)                     → currently broken import
Phase 8  core/annotation/*          (not yet reviewed)
Phase 9  core/engineering/*         (not yet reviewed)
Phase 10 core/reconstruction/*      run_phase10.py                    → viewer meshes (explicitly distrusted per user)
```

There is no `core/__init__.py` and every subpackage `__init__.py` is empty — the pipeline structure above is **implicit** in the sequence of `run_phaseN.py` scripts, not documented as prose anywhere in `core/`. The closest thing to an architecture doc is the module docstring in `core/geometry/canonical.py`, which states the canonical repository is "the single representation consumed by all downstream phases."

`README.md` documents an unrelated, older tool (`rebar_extractor` package, invoked via `python -m rebar_extractor.main`) that does not exist in the repo. It is stale and should either be rewritten or deleted — it currently misleads anyone new to the project.

## 2. Data flow

Single source drawing carries the entire pipeline: **`SS-GF-01(M).dxf`** is the only file in `test_project/` with a registered reader. The other 12 files (`.dwg`, `.pdf`) produce zero entities — Phase 1 logs `"No reader available for extension: dwg/pdf"` and they never enter Phase 2 onward. So everything downstream of Phase 1 has effectively been validated against **one drawing**, not a corpus. This is the single biggest caveat on all claims of correctness in Phases 2–10: they generalize from n=1.

## 3. Verified stages (have automated regression coverage, currently passing)

- **Phase 2** — entity-count regression against `tests/golden/SS-GF-01(M)/phase02/translation_report.json` passes. A separate `run_phase2_audit.py` (5 audits: conservation, fidelity overlay, bbox, UUID stability, provenance) also passes, but **its results are never persisted to disk** — only printed to stdout. If it isn't re-run, there's no artifact proving it ever passed.
- **Phase 3** — canonical entity counts, bbox, and geometry-hash fingerprints regression-tested against golden, currently passing with 0 critical errors / 0 warnings.
- **Phase 6** — node/edge/component metrics and component-UUID stability regression-tested against golden, currently passing on the metrics comparison — **but see §4**, the gate is weaker than the regression test implies.

## 4. Suspect / weak stages

- **Phase 1** — no automated tests at all (`run_phase1_tests.py` has zero `assert` statements, it's a manual dump-and-eyeball script). Duplicate detection and identity parsing work in the one scenario exercised, but there's no regression protection against future breakage.
- **Phase 2 audit** — passes, but non-persistent (see §3). Cheap to fix (write results to `debug/phase02_audit/audit_results.json`), should be done before trusting this phase long-term.
- **Phase 4** — all 11 acceptance checks and benchmarks pass, but explicitly excluded from `tests/regression.py` (comment in `run_phase3.py`: "Phase 4 (stub for completeness, benchmarks normally aren't regressed strictly)"). No regression protection.
- **Phase 5** — 0 duplicate nodes, 0 orphan-node check is embedded inside the script's own validation, but **there is no golden file and no entry in `tests/regression.py` for Phase 5 at all**. It sits, untested, between two phases (4 and 6) that do have some coverage.
- **Phase 6** — this is the most concrete finding. `metrics.json` reports 0 critical errors and the regression suite passes, but `validation.json` carries **20 warnings that the gate ignores**: 19 duplicate topological edges between the same node pairs, and **87 orphan nodes (degree 0)** out of 2360 total nodes (~3.7%). "READY FOR PHASE 7" is printed despite this. These warnings are exactly the kind of defect that would silently propagate into Phase 7 recognition (an orphan node can't be part of any bar/stirrup path; a duplicate edge inflates degree and could throw off family/spacing logic downstream). This is the strongest candidate for "first phase whose output should not yet be trusted at face value," pending the Phase 7 audit.
- **Phase 7 is currently broken**, not just unverified: `tests/regression.py` crashes with `ImportError: cannot import name 'StirrupRecognizer' from core.recognition.recognizers`. `git status` shows `core/recognition/recognizers.py` as locally modified — whatever edit is in flight removed or renamed `StirrupRecognizer` without updating the test. This means **the regression suite has not successfully run end-to-end in its current state**, and nothing from Phase 7 onward has fresh automated verification right now.

## 5. Technical debt / inconsistencies

- Root directory mixes two generations of the tool: legacy scripts (`extract_rebars.py`, `rebar_detector.py`, `cad_reader.py`, `exporter.py`, `main.py`, `spacing.py`, `geometry.py`, `debug_overlay.py`, `test_sequence.py`, `print_standalone.py`) alongside the current phased `core/` pipeline. `README.md` documents the legacy tool only. Recommend either archiving/deleting the legacy scripts or clearly marking them as superseded, and rewriting `README.md` to describe the actual `run_phaseN.py` pipeline.
- DWG/PDF readers are unimplemented (`core/readers/`), so 12 of 13 fixture drawings never get past Phase 1. If the eventual production corpus includes DWG/PDF drawings, the entire audit trail below Phase 1 says nothing about them yet.
- Audit scripts (`run_phase2_audit.py`) that print PASS/FAIL to stdout without writing artifacts should be changed to always emit a JSON result file, consistent with `run_phase3.py`–`run_phase6.py`.
- `tests/golden/` coverage is uneven: Phase 2, 3, 6 have goldens; Phase 1, 4, 5 do not; Phase 7's golden (`tests/golden/phase07/recognition_results.json`) can't currently be checked because the import is broken.

## 6. Assumptions currently being made (implicit, unverified)

- That a single drawing (`SS-GF-01(M).dxf`) is representative enough to validate the pipeline generally.
- That "0 critical errors" is sufficient to gate phase transitions — Phase 6 shows this assumption already lets real defects (orphan nodes, duplicate edges) through silently as "warnings."
- That deterministic UUID5 hashing (Phase 5's `node_uuid`) is sufficient for node identity; this is asserted rather than tested against a golden set (no golden file exists for Phase 5).

## 7. Recommended fixes (before Phase 7+ can be trusted)

1. Fix the `StirrupRecognizer` import break so the regression suite can run end-to-end again.
2. Turn Phase 6's orphan-node and duplicate-edge warnings into either (a) hard failures gating "READY FOR PHASE 7," or (b) an explicitly documented, bounded tolerance with a regression check on the *count* of warnings (currently anything from 0 to unbounded silently passes).
3. Persist `run_phase2_audit.py` results to disk.
4. Add golden/regression coverage for Phase 1, 4, and 5 (currently zero automated protection).
5. Get a second drawing through the pipeline (or implement a DWG/PDF reader) so correctness claims stop resting on n=1.
6. Reconcile/retire the legacy root-level scripts and rewrite `README.md`.

Per-phase detail follows in `audit_phase01.md` through `audit_phase06.md`.

## 8. Phase state (updated after tightening the Phase 6 gate)

"Complete" is not a useful status for this pipeline — it hides the difference between "runs" and "trustworthy." Tracking four states instead:

| Phase | Implemented | Verified | Regression Locked | Frozen |
|---|:---:|:---:|:---:|:---:|
| 1 — Project loading | ✅ | ✅ (manual) | ❌ | ❌ |
| 2 — Geometry translation | ✅ | ✅ | ✅ | ✅ |
| 3 — Canonicalization | ✅ | ✅ | ✅ | ✅ |
| 4 — Spatial query engine | ✅ | ✅ | ❌ | ❌ |
| 5 — Canonical nodes | ✅ | ⚠️ (no golden; orphan-check definition was inconsistent with Phase 6, now reconciled) | ❌ | ❌ |
| 6 — Connectivity graph | ✅ | ✅ (gate tightened; orphan-node false positives resolved; 4/19 duplicate edges still open pending a domain call — see `audit_phase06_defect_classification.md`) | ✅ (now also fails on `errors`, not just `critical_errors`) | ❌ (blocked on the 4 unresolved duplicate-edge pairs) |
| 7 — Recognition | ✅ import bug fixed, golden-path bug fixed | ✅ (verified deterministic: 15/15 identical output hashes; label classification was never wrong, only float summation order was unstable) | ✅ (`tests/determinism.py` added as a permanent 10-run hash check; golden re-baselined) | ❌ (labels/measurements verified stable; recognition *accuracy* — the galleries/confusion-matrix work called for in the original brief — not yet audited) |
| 8-10 | not yet audited this round | — | — | — |

**Phase 7.1 — Determinism audit (this round)**: found and fixed. Root cause was in Phase 1, not Phase 7: `core/identity_parser.py::parse_identity()` called `uuid.uuid4()` to generate each drawing's identity UUID, fresh and random on every `project.load_directory()` call. Every canonical entity UUID downstream is derived from that value (`core/readers/dxf_reader.py:132`), so identical input produced entirely different entity/edge UUIDs each run. That randomness propagated into Python `set` iteration order for edges within a connected component, which made floating-point summation order (and therefore the last few digits of `total_length` and similar aggregate measurements) vary run-to-run — different enough to change the SHA-256 fingerprint, even though the recognized *label* was always correct and stable. Fixed by deriving the identity UUID deterministically from the filename (`uuid5` with a fixed namespace, matching the pattern already used for node/edge/component UUIDs elsewhere in the codebase). Full writeup: `audit_phase07_determinism.md`.
