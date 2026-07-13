"""
tests/test_benchmark.py

Phase 13.1 (validation framework) freeze criteria:
  1. Determinism -- loading the fixture corpus and building reports twice
     produces byte-identical report.json (no timestamps, sorted output).
  2. Fixture regression -- the demo_project fixture must produce the exact
     expected metric values and failure explanations: recall 0.0 with one
     'missed' (N6+N7 held at REVIEW) and one 'unresolvable'
     (drawing_missing), precision undefined-with-note, observation
     coverage 2/3, reconstruction coverage 1.0 (N4 bar exists).
  3. False-merge unit test -- in-memory clusters where one pipeline
     identity spans two GT bars must yield false_merge_rate 1.0,
     precision 0.0, and both GT outcomes explained.
  4. False-split unit test -- one GT bar scattered across two pipeline
     identities must yield false_split_rate 1.0 and a 'split' outcome.
  5. Pipeline-unchanged guardrail -- pipeline output obtained through the
     benchmark loader is identical to output obtained by calling the
     pipeline directly (the benchmark is an evaluation layer only).

Usage:
    python tests/test_benchmark.py     # fixture corpus path is built-in

Exit codes:
    0 — all checks passed
    1 — a check failed
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import uuid

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "benchmark_corpus", "demo_project")


def _report_hash(out_dir: str) -> str:
    with open(os.path.join(out_dir, "report.json"), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_determinism() -> bool:
    from benchmark.loaders.project_loader import load_project
    from benchmark.reports.report_builder import write_reports

    hashes = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as out:
            write_reports([load_project(FIXTURE)], out)
            hashes.append(_report_hash(out))
    ok = hashes[0] == hashes[1]
    print(f"[determinism] 2 full runs -> {'identical' if ok else 'DIVERGED'} ({hashes[0][:12]}...)")
    return ok


def check_fixture_regression() -> bool:
    from benchmark.loaders.project_loader import load_project
    from benchmark.metrics.identity_metrics import compute_identity_metrics
    from benchmark.metrics.coverage_metrics import compute_coverage

    project = load_project(FIXTURE)
    im = compute_identity_metrics(project)
    cm = compute_coverage(project)

    statuses = {o.gt_uuid: o.status for o in im.gt_outcomes}
    unresolvable = next(o for o in im.gt_outcomes if o.gt_uuid == "gt-0002")

    ok = (
        im.precision is None and "zero identities" in im.precision_note
        and im.recall == 0.0
        and im.false_split_rate == 0.0
        and statuses == {"gt-0001": "missed", "gt-0002": "unresolvable"}
        and unresolvable.selector_failures[0]["status"] == "drawing_missing"
        and cm.observation_coverage == 0.667
        and cm.reconstruction_coverage == 1.0
    )
    print(f"[fixture] statuses={statuses}, precision={im.precision} ({im.precision_note[:40]}...), "
          f"recall={im.recall}, obs_cov={cm.observation_coverage}, recon_cov={cm.reconstruction_coverage} "
          f"-> {'OK' if ok else 'MISMATCH'}")
    return ok


def _fake_observation(drawing: str, mark: str):
    from core.fusion.models import DrawingRole, ObservationFact, PhysicalObservation
    obs_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"fake|{drawing}|{mark}")
    return PhysicalObservation(
        uuid=obs_uuid, drawing_filename=drawing, drawing_number="FAKE-GF-01",
        drawing_view="M", drawing_role=DrawingRole("unclassified", 0.0, "fake"),
        family_uuid=uuid.uuid4(), mark_namespace="reference_code", family_type="main_bar",
        bbox=(0, 0, 100, 100),
        facts=[ObservationFact(uuid.uuid4(), "mark", mark, 1.0, "fake")],
    )


def _fake_project(observations, identity_obs_sets, gt_entries):
    from benchmark.loaders.project_loader import BenchmarkProject, GroundTruthIdentity
    from core.fusion.models import PhysicalIdentity

    identities = [
        PhysicalIdentity(
            uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"fake-id|{i}"),
            observations=sorted(obs_set, key=str),
        )
        for i, obs_set in enumerate(identity_obs_sets)
    ]
    gt = [
        GroundTruthIdentity(
            uuid=g["uuid"], name=g["uuid"], mark=None, diameter=None, spacing=None,
            role=None, observations=g["observations"],
        )
        for g in gt_entries
    ]
    return BenchmarkProject(
        name="fake", path="fake", metadata={"labeled_by": "unit test"},
        gt_identities=gt, gt_bars=[], gt_families=[],
        observations=observations, decisions=[], identities=identities,
        physical_bars=[], drawings_processed=1,
    )


def check_false_merge() -> bool:
    from benchmark.metrics.identity_metrics import compute_identity_metrics

    a = _fake_observation("d1.dxf", "N1")
    b = _fake_observation("d1.dxf", "N2")
    project = _fake_project(
        observations=[a, b],
        identity_obs_sets=[[a.uuid, b.uuid]],   # one identity spanning both GT bars
        gt_entries=[
            {"uuid": "gt-A", "observations": [{"drawing": "d1.dxf", "mark": "N1"}]},
            {"uuid": "gt-B", "observations": [{"drawing": "d1.dxf", "mark": "N2"}]},
        ],
    )
    im = compute_identity_metrics(project)
    merged_statuses = {o.gt_uuid: o.status for o in im.gt_outcomes}
    ok = (
        im.false_merge_rate == 1.0
        and im.precision == 0.0
        and im.pipeline_outcomes[0].status == "false_merge"
        and merged_statuses == {"gt-A": "merged", "gt-B": "merged"}
    )
    print(f"[false-merge] rate={im.false_merge_rate}, precision={im.precision}, "
          f"gt={merged_statuses} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_false_split() -> bool:
    from benchmark.metrics.identity_metrics import compute_identity_metrics

    a = _fake_observation("d1.dxf", "N1")
    b = _fake_observation("d2.dxf", "N1")
    project = _fake_project(
        observations=[a, b],
        identity_obs_sets=[[a.uuid], [b.uuid]],   # one GT bar split across two identities
        gt_entries=[
            {"uuid": "gt-A", "observations": [
                {"drawing": "d1.dxf", "mark": "N1"}, {"drawing": "d2.dxf", "mark": "N1"},
            ]},
        ],
    )
    im = compute_identity_metrics(project)
    outcome = im.gt_outcomes[0]
    ok = im.false_split_rate == 1.0 and outcome.status == "split" and len(outcome.matched_pipeline_identities) == 2
    print(f"[false-split] rate={im.false_split_rate}, status={outcome.status} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_pipeline_unchanged() -> bool:
    """The benchmark loader must produce exactly the pipeline's own output
    -- same observations, same decisions, same identities -- proving it is
    an evaluation layer, not a behavioral one."""
    from benchmark.loaders.project_loader import load_project
    from core.full_pipeline import run_pipeline_through_phase9
    from core.fusion.observation_builder import build_observations
    from core.fusion.hypothesis_generator import generate_hypotheses
    from core.fusion.evidence_engine import score_hypotheses
    from core.fusion.identity_resolver import resolve_identities

    drawings_dir = os.path.join(FIXTURE, "drawings")
    results = list(run_pipeline_through_phase9(drawings_dir))
    observations = build_observations(results)
    scored = score_hypotheses(generate_hypotheses(observations), observations)
    decisions, identities = resolve_identities(scored, observations)

    project = load_project(FIXTURE)
    ok = (
        [o.uuid for o in project.observations] == [o.uuid for o in observations]
        and [d.uuid for d in project.decisions] == [d.uuid for d in decisions]
        and [i.uuid for i in project.identities] == [i.uuid for i in identities]
    )
    print(f"[unchanged] loader output == direct pipeline output "
          f"({len(observations)} obs, {len(decisions)} decisions) -> {'OK' if ok else 'DIVERGED'}")
    return ok


def run_check() -> int:
    results = [
        check_determinism(),
        check_fixture_regression(),
        check_false_merge(),
        check_false_split(),
        check_pipeline_unchanged(),
    ]
    if all(results):
        print("\nPHASE 13.1 BENCHMARK CHECKS PASSED ✅")
        return 0
    print("\nPHASE 13.1 BENCHMARK CHECKS FAILED ❌")
    return 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    sys.exit(run_check())
