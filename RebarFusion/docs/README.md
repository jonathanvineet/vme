# RebarFusion — Documentation Index

## Status: Phases 1-10 frozen (v1.0)

| Phase | Status | Audits |
|---|---|---|
| 1 — Project Manager | ✅ Frozen | [audit](audits/phase01/audit.md) |
| 2 — Geometry Translation | ✅ Frozen | [audit](audits/phase02/audit.md) |
| 3 — Canonicalization | ✅ Frozen | [audit](audits/phase03/audit.md) |
| 4 — Spatial Index | ✅ Frozen | [audit](audits/phase04/audit.md) |
| 5 — Canonical Nodes | ✅ Frozen | [audit](audits/phase05/audit.md) |
| 6 — Topology | ✅ Frozen (1 documented ambiguity) | [audit](audits/phase06/audit.md), [defect classification](audits/phase06/defect_classification.md) |
| 7 — Recognition | ✅ Frozen | [determinism](audits/phase07/determinism.md), [accuracy v1](audits/phase07/7.5_recognition_accuracy_v1.md) → [v2](audits/phase07/7.5_recognition_accuracy_v2.md), [plausibility](audits/phase07/7.6_physical_plausibility.md), [fragment audit](audits/phase07/7.7_geometry_fragment.md) |
| 8 — Engineering Association | ✅ Frozen | [association](audits/phase08/association.md), [leader reconstruction](audits/phase08/leader_reconstruction.md) |
| 9 — Engineering Families | ✅ Frozen | [families](audits/phase09/families.md), [9.1 mark provenance](audits/phase09/9.1_mark_provenance.md), [9.2 standalone provenance](audits/phase09/9.2_standalone_provenance.md), [9.3 spacing validation](audits/phase09/9.3_spacing_validation.md), [9.4 confidence decomposition](audits/phase09/9.4_confidence_decomposition.md) |
| 10 — Digital Twin Reconstruction | ✅ Frozen | [10.0 initial audit](audits/phase10/10.0_reconstruction_audit.md), [10.1 geometry recovery redesign](audits/phase10/10.1_geometry_recovery_redesign.md), [10.2 tube sweep design](audits/phase10/10.2_continuous_tube_sweep.md), [10.3 tube sweep implementation](audits/phase10/10.3_continuous_tube_sweep_implementation.md), [10.4 regression audit / freeze](audits/phase10/10.4_reconstruction_regression_audit.md) |
| 11.0/11.1 — Engineering Viewer (pipeline modernization) | ✅ Frozen | [11.0 viewer audit](audits/phase11/11.0_viewer_audit.md), [11.1 pipeline modernization](audits/phase11/11.1_viewer_pipeline_modernization.md) |
| 11.2 — Engineering Viewer (new capabilities) | ⬜ Not started | — |
| 12 — Physical Identity Resolution (research) | ✅ Research complete | [research report](research/phase12_cross_view_fusion_research.md) |
| 12.1 — Observation Builder | ✅ Frozen (revised) | [audit](audits/phase12/12.1_observation_builder.md) |
| 12.2 — Hypothesis Generator | ✅ Frozen | [audit](audits/phase12/12.2_hypothesis_generator.md) |
| 12.3 — Evidence Engine | ✅ Frozen | [audit](audits/phase12/12.3_evidence_engine.md) |
| 12.4 — Identity Resolver | ✅ Frozen | [audit](audits/phase12/12.4_identity_resolver.md) |
| 13.0 — DWG Ingestion (ODA converter) | ✅ Frozen | [audit](audits/phase13/13.0_dwg_ingestion.md) |
| 13.1 — Validation Corpus & Benchmark | ✅ Frozen (corpus awaits real labeled projects) | [audit](audits/phase13/13.1_validation_framework.md) |
| 13.2 — Engineering Validation Dataset | → **CURRENT** (Apollo drafted, pending engineer verification; target 10-20 projects) | [Apollo audit](audits/phase13/13.2_apollo_ground_truth.md), [corpus guide](../benchmark/corpus/README.md) |

Roadmap / north star: [roadmap.md](roadmap.md). Engineering-domain assumptions: [engineering_assumptions.md](engineering_assumptions.md).

Overall pipeline architecture and the original Step-1 review: [architecture_review.md](architecture/architecture_review.md).

## How to read this audit trail

These audits were written in sequence, each building on the last. They record not just what was found but the *reasoning* — including two cases where a working hypothesis was tested and disproven (Phase 9.1's original `_seed_bars` propagation theory, corrected to the true "mark broadcast" root cause; Phase 9.3's assumption that spacing used naive centroid distance, found to already be correct). Read them in order within a phase if you want the full reasoning; read [known_limitations.md](known_limitations.md) if you just want the current, honest state.

## Regenerating evidence

- `tests/determinism.py <directory> [--runs N]` — pipeline output must hash-identical across N runs.
- `tests/regression.py <directory>` — golden-file checks for Phases 2/3/6/7.
- `run_phaseN.py <directory>` — runs phase N standalone, writes fresh debug artifacts to `debug/phaseNN/<drawing>/`.
