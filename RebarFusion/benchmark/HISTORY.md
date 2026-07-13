# Benchmark History

Git history for engineering performance. Every milestone benchmark run gets one entry — corpus state, engineer investment, headline metrics, and what changed. Numbers come from `run_benchmark.py benchmark/corpus`; a run becomes a milestone when the corpus, the labels, or the pipeline changed meaningfully, not on every invocation.

## Progression

| Date | Corpus | Projects | Engineer hours | Precision | Recall | False merge | False split | Obs cov | Eng cov | Recon cov |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-13 | Apollo (draft) | 1 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.889 | 0.838 | 1.000 |
| — | Apollo (verified) | 1 | ? | ? | ? | ? | ? | ? | ? | ? |
| — | Corpus v0.2 (~5 projects) | | | | | | | | | |
| — | Corpus v1.0 (~20 projects) | | | | | | | | | |

## Milestones

### 2026-07-13 — First independently-labelled benchmark (Apollo draft)

- **Corpus**: Apollo — 8 drawings, 18 draft GT identities, 7 bar marks. Labels are a provenance-tracked AI-assistant draft; `engineer_hours: 0` until verified.
- **Pipeline**: v1.0-alpha + Phase 13.0 DWG ingestion (frozen; nothing tuned for this run).
- **Headline**: precision/recall 0.000 with 1196/1198 pair decisions at REVIEW — the conservative resolver refusing to invent identities it cannot justify, measured for the first time. 1 ACCEPTED (the A17/VQ-001 T16 pair, correctness unresolved), 1 REJECTED.
- **Found by the benchmark**: 2 Recognition/Association failures (PW-GF-09(M1)'s N7/N8 dowel annotations exist in raw text but produce no observations); the pipeline's `N4 diameter=8.0` formally contradicted by ground truth (was a suspicion, now a measured discrepancy); same-mark selector granularity limit (schema v1).
- **Open**: VQ-001 (docs/validation_questions.md) — T16 grouping on PW-GF-09(R).
- **Audit**: `docs/audits/phase13/13.2_apollo_ground_truth.md`.
