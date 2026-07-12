"""
tests/test_phase12_hypothesis_generator.py

Phase 12.2 freeze criteria:
  1. Determinism -- generate_hypotheses() produces an identical JSON hash
     across repeated runs on the same directory.
  2. Real-data regression -- against SS-GF-01(M).dxf's 3 observations,
     N6 and N7 must become mutual candidates (via fact_agreement on
     shape/orientation/quantity, corroborated by a ~1.9m centroid
     distance) while N4 gets zero candidates (its facts conflict with
     both). This reproduces, from independent non-spatial evidence, the
     "N6/N7 belong to one upstand detail" relationship the research
     report found by visual inspection.
  3. Synthetic three-observation acceptance criterion -- the original
     Phase 12.0 acceptance criteria (plan + section + schedule, all
     marked N7, should be recognized as candidates of one another) but
     scoped correctly to what Phase 12.2 actually produces: a mutual
     PENDING candidate grouping, not a resolved PhysicalIdentity.
  4. Completeness -- a pair with real evidence that DOESN'T qualify
     (e.g. a fact conflict) must still appear in the evidence trail, not
     be silently dropped. "Generate every plausible candidate, then
     score, then reject" (Addendum 3) means the trail has to survive
     even for rejected-at-this-stage pairs.
  5. No-decisions guardrail -- every IdentityHypothesis.status is PENDING
     (Phase 12.2 never sets ACCEPTED/REJECTED), and HypothesisEvidence
     carries no numeric score field (scoring is Phase 12.3's job, not
     this one's).

Usage:
    python tests/test_phase12_hypothesis_generator.py <directory>

Exit codes:
    0 — all checks passed
    1 — a check failed
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, fields, is_dataclass


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


def _hash(obj) -> str:
    payload = json.dumps(obj, sort_keys=True, cls=_Encoder)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pipeline(directory: str):
    from core.full_pipeline import run_pipeline_through_phase9
    from core.fusion.observation_builder import build_observations
    from core.fusion.hypothesis_generator import generate_hypotheses

    results = list(run_pipeline_through_phase9(directory))
    observations = build_observations(results)
    hypotheses = generate_hypotheses(observations)
    return observations, hypotheses


def check_determinism(directory: str, runs: int = 5) -> bool:
    hashes = [_hash(_pipeline(directory)[1]) for _ in range(runs)]
    ok = len(set(hashes)) == 1
    print(f"[determinism] {runs} runs -> {'identical' if ok else 'DIVERGED'} ({hashes[0][:12]}...)")
    return ok


def check_real_data_regression(directory: str) -> bool:
    from core.fusion.models import ASPECT_MARK

    observations, hypotheses = _pipeline(directory)
    by_uuid = {o.uuid: o for o in observations}

    def mark_of(obs_uuid):
        obs = by_uuid[obs_uuid]
        f = obs.fact(ASPECT_MARK)
        return f.value if f else None

    by_mark = {}
    for h in hypotheses:
        by_mark[mark_of(h.anchor_observation)] = {mark_of(c) for c in h.candidate_observations}

    ok = (
        by_mark.get("N4") == set()
        and by_mark.get("N6") == {"N7"}
        and by_mark.get("N7") == {"N6"}
    )
    print(f"[real-data] N4->{by_mark.get('N4')}, N6->{by_mark.get('N6')}, "
          f"N7->{by_mark.get('N7')} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_completeness(directory: str) -> bool:
    """N4's hypothesis has zero candidates but must still carry evidence
    explaining what was considered and why it was excluded (fact
    conflicts) -- not an empty evidence list."""
    from core.fusion.models import ASPECT_MARK

    observations, hypotheses = _pipeline(directory)
    by_uuid = {o.uuid: o for o in observations}
    n4_hyp = next(
        h for h in hypotheses
        if by_uuid[h.anchor_observation].fact(ASPECT_MARK)
        and by_uuid[h.anchor_observation].fact(ASPECT_MARK).value == "N4"
    )
    has_conflict_evidence = any(e.rule == "fact_conflict" for e in n4_hyp.evidence)
    ok = len(n4_hyp.candidate_observations) == 0 and has_conflict_evidence
    print(f"[completeness] N4 hypothesis: {len(n4_hyp.candidate_observations)} candidate(s), "
          f"{len(n4_hyp.evidence)} evidence item(s), conflict evidence present={has_conflict_evidence} "
          f"-> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_synthetic_three_observation_grouping() -> bool:
    """The original Phase 12.0 acceptance criterion: plan + section +
    schedule, all marked N7, should be recognized as candidates of one
    another. Scoped to what 12.2 actually produces (PENDING mutual
    candidates), not a resolved identity."""
    from core.fusion.observation_builder import NAMESPACE_FACT
    from core.fusion.models import (
        ASPECT_DIAMETER, ASPECT_LENGTH, ASPECT_MARK, ASPECT_POSITION,
        ASPECT_QUANTITY, DrawingRole, ObservationFact, PhysicalObservation,
    )
    from core.fusion.hypothesis_generator import generate_hypotheses

    def _fact(obs_uuid, aspect, value, confidence=1.0):
        return ObservationFact(
            uuid=uuid.uuid5(NAMESPACE_FACT, f"{obs_uuid}|{aspect}"),
            aspect=aspect, value=value, confidence=confidence, source="synthetic",
        )

    plan_uuid, section_uuid, schedule_uuid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    unclassified_role = DrawingRole(role="unclassified", confidence=0.0, evidence="synthetic fixture")

    plan = PhysicalObservation(
        uuid=plan_uuid, drawing_filename="plan.dxf", drawing_number="PW-GF-09", drawing_view="M1",
        drawing_role=unclassified_role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[_fact(plan_uuid, ASPECT_MARK, "N7"), _fact(plan_uuid, ASPECT_POSITION, (100.0, 200.0))],
    )
    section = PhysicalObservation(
        uuid=section_uuid, drawing_filename="section.dxf", drawing_number="PW-GF-09", drawing_view="M2",
        drawing_role=unclassified_role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[_fact(section_uuid, ASPECT_MARK, "N7"), _fact(section_uuid, ASPECT_DIAMETER, 16.0)],
    )
    schedule = PhysicalObservation(
        uuid=schedule_uuid, drawing_filename="schedule.dxf", drawing_number="PW-GF-09", drawing_view="SCHEDULE",
        drawing_role=unclassified_role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[
            _fact(schedule_uuid, ASPECT_MARK, "N7"), _fact(schedule_uuid, ASPECT_DIAMETER, 16.0),
            _fact(schedule_uuid, ASPECT_QUANTITY, 6), _fact(schedule_uuid, ASPECT_LENGTH, 2850.0),
        ],
    )

    hypotheses = generate_hypotheses([plan, section, schedule])
    by_anchor = {h.anchor_observation: h for h in hypotheses}

    ok = (
        len(hypotheses) == 3
        and set(by_anchor[plan_uuid].candidate_observations) == {section_uuid, schedule_uuid}
        and set(by_anchor[section_uuid].candidate_observations) == {plan_uuid, schedule_uuid}
        and set(by_anchor[schedule_uuid].candidate_observations) == {plan_uuid, section_uuid}
        and all(h.status == "PENDING" for h in hypotheses)
    )
    print(f"[synthetic-N7] plan/section/schedule mutually grouped, all PENDING -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_no_decisions(directory: str) -> bool:
    """Guardrail: Phase 12.2 must never set status away from PENDING, and
    must never populate Evidence.confidence -- that field exists on the
    shared type (added for Phase 12.3 to fill in) but Phase 12.2's own
    generator must leave every instance it produces at None. Checked
    against real data, not just the dataclass shape, since the field
    existing is correct now (Phase 12.3 needs it) -- what must hold is
    that 12.2 never writes to it."""
    from core.fusion.models import IdentityHypothesis

    _, hypotheses = _pipeline(directory)
    all_pending = all(h.status == "PENDING" for h in hypotheses)
    no_confidence_populated = all(e.confidence is None for h in hypotheses for e in h.evidence)

    hypothesis_fields = {f.name for f in fields(IdentityHypothesis)}
    forbidden_hypothesis = {"resolved_identity_uuid", "physical_identity"}
    leaked_hypothesis = hypothesis_fields & forbidden_hypothesis

    ok = all_pending and no_confidence_populated and not leaked_hypothesis
    print(f"[guardrail] all hypotheses PENDING: {all_pending}; no Evidence.confidence "
          f"populated by 12.2: {no_confidence_populated} -> {'OK' if ok else 'LEAKED'}")
    return ok


def run_check(directory: str) -> int:
    results = [
        check_determinism(directory),
        check_real_data_regression(directory),
        check_completeness(directory),
        check_synthetic_three_observation_grouping(),
        check_no_decisions(directory),
    ]
    if all(results):
        print("\nPHASE 12.2 CHECKS PASSED ✅")
        return 0
    print("\nPHASE 12.2 CHECKS FAILED ❌")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_phase12_hypothesis_generator.py <directory>")
        sys.exit(1)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    sys.exit(run_check(sys.argv[1]))
