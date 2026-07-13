# Known Limitations (Phases 1-10, v1.0 freeze)

Consolidated from the individual phase audits. Each item links back to the audit that found it. None of these block the v1.0 freeze — they're documented, bounded, and understood, which is the bar this project has held throughout.

## Phase 6 — Topology
**4 ambiguous duplicate-edge pairs** (`A-FLOR` arcs, sequential native handles, no block) remain unclassified as intentional-convention vs. drafting-accident. 15 of the original 19 duplicate-edge pairs were resolved with high confidence; these 4 need a domain/drafting call, not a pipeline fix.
→ [audit_phase06/defect_classification.md](audits/phase06/defect_classification.md)

## Phase 7.7 — Geometry Fragment Audit
**32 of 70 flagged fragments remain unresolved.** The dominant cluster (38/70, 54%) was conclusively traced to one repeated CAD drafting symbol and classified. The remaining 32 are heterogeneous singleton lengths (1.6mm-29.2mm) with no shared signature — genuinely different cases, not one bug, honestly left unclassified rather than forced into the resolved cluster's explanation.
→ [audits/phase07/7.7_geometry_fragment.md](audits/phase07/7.7_geometry_fragment.md)

## Phase 7.6/7.7 — Deferred plausibility rule
An **isolation-based plausibility rule** (reject components with no nearby geometry) was identified as well-justified by the fragment audit but deliberately **not implemented** — it would need validation across multiple drawings first to avoid overfitting to this one drawing's exact fragment pattern (risk: suppressing legitimate isolated hooks/ties on a different project).
→ [audits/phase07/7.7_geometry_fragment.md](audits/phase07/7.7_geometry_fragment.md)

## Phase 9 — Thin dataset for spacing/confidence validation
Only 1 of 3 families in the test drawing has measurable spacing (≥2 members), and that family (N4) is built from components entangled with the Phase 7.7 fragment cluster. Spacing/confidence **measurement methodology** is validated (both were checked against naive/incorrect alternatives and found already correct or were fixed), but real-world **accuracy** validation needs either a second drawing or resolution of the fragment question.
→ [audits/phase09/9.3_spacing_validation.md](audits/phase09/9.3_spacing_validation.md), [audits/phase09/9.4_confidence_decomposition.md](audits/phase09/9.4_confidence_decomposition.md)

## Phase 9 — Cross-family conflict rule not implemented
`cross_family_marks` (Phase 9) reports when multiple families share a mark, but purely informationally — no rule yet distinguishes "legitimate repeated mark across separate physical bar groups" from "should have been one family, fragmented in error." Deferred pending more evidence on what a real conflict looks like vs. a legitimate repeat.
→ [audits/phase09/9.1_mark_provenance.md](audits/phase09/9.1_mark_provenance.md)

## Phase 10 — Viewer-readiness wiring gaps (Phase 11 setup work, not a Phase 10 defect)
`PhysicalBar`/`ReconstructionMesh` don't yet carry Phase 9's QA/standalone/spacing-outlier data directly (it exists, joinable via `family_uuid`/`member_uuid`, just not pre-attached), and neither carries a precomputed `BoundingBox` (trivial to add from `mesh.vertices`, just not done yet). Neither affects reconstruction correctness — both are Phase 11 (viewer) wiring convenience, deferred until the viewer actually needs them.
→ [audits/phase10/10.4_reconstruction_regression_audit.md](audits/phase10/10.4_reconstruction_regression_audit.md)

## Phase 10 — Deferred, not yet observed as a problem
Closed-loop (stirrup) parallel-transport frame continuity: a potential small holonomy mismatch between the seed and final frame at the seam of a closed tube. No stirrup family exists in the current dataset to test against — flagged as a fix to make when a real closed-loop case surfaces an actual artifact, not preemptively.
→ [audits/phase10/10.2_continuous_tube_sweep.md](audits/phase10/10.2_continuous_tube_sweep.md)

## Phase 11.1 — Bundle export not yet restructured
Bundle version compatibility is genuinely enforced (`BundleVersionMismatch`, verified both accept and reject), but bundles are still assembled by scanning scattered `debug/phaseNN/` files rather than a single purpose-built `output/workbench/` export with its own manifest. Worth doing before Phase 11.2's new features; not required for the Phase 11.1 modernization itself to be sound.
→ [audits/phase11/11.1_viewer_pipeline_modernization.md](audits/phase11/11.1_viewer_pipeline_modernization.md)

## Phase 11.1 — No visual treatment for rejected/flagged fragments yet
`WorkbenchProject.plausibility` is now populated (Phase 7.6 data reaches the viewer), but no renderer uses it yet to visually distinguish rejected/review-flagged components (e.g. gray color, QA badge). This is new-feature work for Phase 11.2, not a modernization gap — the data exists, nothing consumes it yet.
→ [audits/phase11/11.1_viewer_pipeline_modernization.md](audits/phase11/11.1_viewer_pipeline_modernization.md)

## Phase 12.4 — The one real PhysicalIdentity needs engineering verification
DWG ingestion (Phase 13.0) gave Phase 12 real multi-view data: 8 drawings, 88 observations, 1100 pair-decisions. Exactly one pair reached `ACCEPTED` — two `T16` families, both from `PW-GF-09(R).dwg` (same sheet). This is either the same physical bars drawn in the sheet's elevation and section views (legitimate fusion) or two distinct T16 bar groups sharing a mark (a false merge); no automated evidence distinguishes the two yet, so the identity is **unverified**, flagged rather than trusted. Separately: all cross-drawing `SS-GF-01(M)`↔`(R)` pairs land in `REVIEW` because N-code → T-mark resolution requires the schedule/annotation lookup mechanism (evidence categories named in Phase 12.3 but with no generators) — designed behavior, but it means genuine cross-*drawing* identity acceptance has still never happened on real data.
→ [audits/phase13/13.0_dwg_ingestion.md](audits/phase13/13.0_dwg_ingestion.md)

## Phase 1 — Duplicate tie-break keeps arbitrary filename
`banana.dwg`, `PW-GF-02(M1).dwg`, and `PW-GF-02(M1)-copy.dwg` are byte-identical; Phase 1 keeps whichever `os.walk` yields first (`banana.dwg`) and marks the properly-named files as duplicates, so 3 observations carry an unparseable filename and an `unclassified` drawing role. Pre-existing behavior surfaced by DWG unlock; fix is a tie-break rule preferring the filename that parses as a drawing identity.
→ [audits/phase13/13.0_dwg_ingestion.md](audits/phase13/13.0_dwg_ingestion.md)

## Structural
- **Single-drawing validation only — LIFTED by Phase 13.0** for the 9 `.dwg` files (now converted via the locally-pinned ODA File Converter and read through the same frozen DXF parser). Historical caveat that remains true: every audit from Phase 2 through 12.4 was *conducted* against `SS-GF-01(M).dxf` alone; those phases now *run* against 8 drawings but have not been re-audited against them. The 4 `.pdf` files remain unread (print duplicates of now-readable DWG sheets).
- **Legacy code at repo root** (`extract_rebars.py`, `rebar_detector.py`, `cad_reader.py`, etc.) predates the phased `core/` pipeline and was never audited or reconciled — flagged in the original architecture review, still unresolved.
