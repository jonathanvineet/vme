"""
run_phase12.py — Phase 12.1/12.2: Observation Builder + Hypothesis Generator

Runs Phases 1-9 (via core/full_pipeline.py) across every readable drawing
in a project directory, builds PhysicalObservation records from their
EngineeringFamily output, then generates IdentityHypothesis records (who
could each observation be?). Writes debug/phase12/<project>/observations.json
and hypotheses.json.

This does NOT score evidence, accept/reject hypotheses, resolve identity,
or reconstruct geometry -- Phase 12.2 stops at PENDING hypotheses. See
docs/audits/phase12/12.1_observation_builder.md and 12.2_hypothesis_generator.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, is_dataclass

from core.full_pipeline import run_pipeline_through_phase9
from core.fusion.observation_builder import build_observations
from core.fusion.hypothesis_generator import generate_hypotheses
from core.fusion.evidence_engine import score_hypotheses


class ObservationEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


def _jdump(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, cls=ObservationEncoder)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 12.1: Observation Builder")
    parser.add_argument("directory", help="Project directory to scan")
    args = parser.parse_args()

    project_name = os.path.basename(os.path.normpath(args.directory))
    out_dir = os.path.join("debug", "phase12", project_name)
    os.makedirs(out_dir, exist_ok=True)

    results = list(run_pipeline_through_phase9(args.directory))
    observations = build_observations(results)
    hypotheses = generate_hypotheses(observations)
    scored = score_hypotheses(hypotheses, observations)

    _jdump(os.path.join(out_dir, "observations.json"), observations)
    _jdump(os.path.join(out_dir, "hypotheses.json"), hypotheses)
    _jdump(os.path.join(out_dir, "scored_hypotheses.json"), scored)

    print(f"Drawings processed: {len(results)}")
    print(f"Observations built: {len(observations)}")
    by_role = {}
    for obs in observations:
        by_role.setdefault(obs.drawing_role.role, 0)
        by_role[obs.drawing_role.role] += 1
    for role, count in sorted(by_role.items()):
        print(f"  {role}: {count}")
    for obs in observations:
        aspects = ", ".join(sorted(f.aspect for f in obs.facts))
        print(f"  observation {str(obs.uuid)[:8]}: aspects=[{aspects}]")

    print(f"\nHypotheses generated: {len(hypotheses)}")
    with_candidates = [h for h in hypotheses if h.candidate_observations]
    print(f"  with >=1 candidate: {len(with_candidates)}")
    print(f"  with 0 candidates (no plausible cross-view match found): "
          f"{len(hypotheses) - len(with_candidates)}")
    for h in hypotheses:
        if h.candidate_observations:
            print(f"  anchor {str(h.anchor_observation)[:8]}: "
                  f"{len(h.candidate_observations)} candidate(s), {len(h.evidence)} evidence item(s)")

    print("\nScored candidates:")
    for sh in scored:
        for sc in sh.scored_candidates:
            print(f"  {str(sc.anchor_observation)[:8]} -> {str(sc.candidate_observation)[:8]}: "
                  f"overall={sc.score.overall}, categories={sc.score.category_scores}, "
                  f"unscored={sc.score.unscored_categories}")

    print(f"\nWrote {out_dir}/observations.json")
    print(f"Wrote {out_dir}/hypotheses.json")
    print(f"Wrote {out_dir}/scored_hypotheses.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
