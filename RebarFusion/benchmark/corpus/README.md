# Validation Corpus

Each subdirectory here is one complete engineering drawing package with engineer-authored ground truth. Format: `benchmark/schemas/ground_truth_format.md`.

**Currently empty of real projects.** The framework is validated against `tests/fixtures/benchmark_corpus/demo_project/` (synthetic labels, metric-math testing only — explicitly not engineering ground truth). Meaningful precision/recall numbers require real packages labeled by an engineer.

## Onboarding a project

1. Create `<ProjectName>/drawings/` and copy the full package in (`.dxf`/`.dwg`; DWG needs the ODA converter — `scripts/setup_oda.sh`).
2. Have an engineer author `ground_truth/identities.json`: one entry per physical bar, listing every drawing+mark where it appears. This is the labor-intensive step and the entire value of the corpus — it cannot be generated.
3. Add `metadata.json` with the engineer's name and date. The loader rejects ground truth that declares itself machine-generated.
4. Run `python run_benchmark.py benchmark/corpus`.

## Target

10-20 complete precast packages (plan, reinforcement, mould, sections, details, schedules) across multiple consultants/drafting styles. One project validates architecture; only a corpus validates engineering reasoning.
