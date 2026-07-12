"""
tests/test_phase12_identity_resolver.py

Phase 12.4 freeze criteria:
  1. Determinism.
  2. Real-data regression -- N6<->N7 must resolve to a single REVIEW
     decision (a real conflict on real data, not manufactured), and zero
     PhysicalIdentity objects should exist yet -- this project has no
     real candidate pair with unanimous, conflict-free evidence today.
  3. Decision preservation -- REVIEW/REJECTED decisions are never
     discarded; every scored candidate pair produces exactly one
     ResolutionDecision, deduped across the two directions
     generate_hypotheses produces for the same real pair.
  4. Synthetic ACCEPTED case -- a hand-built pair with unanimous,
     conflict-free evidence must resolve to ACCEPTED and produce exactly
     one PhysicalIdentity with both observations, one Claim per
     observation (facts copied verbatim), a decision_uuid, and a
     provenance list containing that decision.
  5. Transitive clustering -- A-B accepted and B-C accepted (A-C never
     directly compared) must merge into ONE PhysicalIdentity of three
     observations, not two separate identities -- proves union-find
     connected components, not just pairwise grouping.
  6. Boundary guardrail -- core/fusion/identity_resolver.py must not
     import anything from core.reconstruction (no geometry allowed in
     this subphase).

Usage:
    python tests/test_phase12_identity_resolver.py <directory>

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
from dataclasses import asdict, is_dataclass


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
    from core.fusion.evidence_engine import score_hypotheses
    from core.fusion.identity_resolver import resolve_identities

    results = list(run_pipeline_through_phase9(directory))
    observations = build_observations(results)
    hypotheses = generate_hypotheses(observations)
    scored = score_hypotheses(hypotheses, observations)
    decisions, identities = resolve_identities(scored, observations)
    return observations, decisions, identities


def check_determinism(directory: str, runs: int = 5) -> bool:
    hashes = [_hash(_pipeline(directory)[1:]) for _ in range(runs)]
    ok = len(set(hashes)) == 1
    print(f"[determinism] {runs} runs -> {'identical' if ok else 'DIVERGED'} ({hashes[0][:12]}...)")
    return ok


def check_real_data_regression(directory: str) -> bool:
    observations, decisions, identities = _pipeline(directory)
    ok = (
        len(decisions) == 1
        and decisions[0].outcome == "REVIEW"
        and 0.0 < decisions[0].overall_confidence < 1.0
        and len(identities) == 0
    )
    print(f"[real-data] {len(decisions)} decision(s), outcome={decisions[0].outcome if decisions else None}, "
          f"confidence={decisions[0].overall_confidence if decisions else None}, "
          f"{len(identities)} identities -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_decision_preservation(directory: str) -> bool:
    """The REVIEW decision must still carry its full rationale (the same
    evidence Phase 12.3 scored) even though it produced no identity."""
    _, decisions, _ = _pipeline(directory)
    d = decisions[0]
    ok = len(d.rationale) > 0 and not d.promoted
    print(f"[preservation] REVIEW decision carries {len(d.rationale)} rationale item(s), "
          f"promoted={d.promoted} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def _synthetic_scored_pair(overrides_a=None, overrides_b=None):
    """Two observations with unanimous, conflict-free evidence: same mark,
    same namespace, agreeing facts, no fact_conflict anywhere -- engineered
    so every scored category comes out to exactly 1.0."""
    from core.fusion.observation_builder import NAMESPACE_FACT
    from core.fusion.models import (
        ASPECT_DIAMETER, ASPECT_MARK, ASPECT_SHAPE, DrawingRole, ObservationFact, PhysicalObservation,
    )

    def _fact(obs_uuid, aspect, value, confidence=1.0):
        return ObservationFact(
            uuid=uuid.uuid5(NAMESPACE_FACT, f"{obs_uuid}|{aspect}"),
            aspect=aspect, value=value, confidence=confidence, source="synthetic",
        )

    a_uuid, b_uuid = uuid.uuid4(), uuid.uuid4()
    role = DrawingRole(role="unclassified", confidence=1.0, evidence="synthetic fixture")
    a = PhysicalObservation(
        uuid=a_uuid, drawing_filename="a.dxf", drawing_number="TEST-ELEMENT", drawing_view="M1",
        drawing_role=role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[_fact(a_uuid, ASPECT_MARK, "N9"), _fact(a_uuid, ASPECT_SHAPE, "branch"),
               _fact(a_uuid, ASPECT_DIAMETER, 16.0)],
    )
    b = PhysicalObservation(
        uuid=b_uuid, drawing_filename="b.dxf", drawing_number="TEST-ELEMENT", drawing_view="M2",
        drawing_role=role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[_fact(b_uuid, ASPECT_MARK, "N9"), _fact(b_uuid, ASPECT_SHAPE, "branch"),
               _fact(b_uuid, ASPECT_DIAMETER, 16.0)],
    )
    return a, b


def check_synthetic_accepted() -> bool:
    from core.fusion.hypothesis_generator import generate_hypotheses
    from core.fusion.evidence_engine import score_hypotheses
    from core.fusion.identity_resolver import resolve_identities

    a, b = _synthetic_scored_pair()
    hyps = generate_hypotheses([a, b])
    scored = score_hypotheses(hyps, [a, b])
    decisions, identities = resolve_identities(scored, [a, b])

    d = next((x for x in decisions if {x.anchor_observation, x.candidate_observation} == {a.uuid, b.uuid}), None)
    ok = (
        d is not None and d.outcome == "ACCEPTED" and d.promoted
        and len(identities) == 1
        and set(identities[0].observations) == {a.uuid, b.uuid}
        and len(identities[0].claims) == 2
        and all(len(c.facts) > 0 for c in identities[0].claims)
        and identities[0].decision_uuid == d.uuid
        and d.uuid in identities[0].provenance
    )
    print(f"[synthetic-accept] decision={d.outcome if d else None}, "
          f"identities={len(identities)}, claims={len(identities[0].claims) if identities else 0} "
          f"-> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_transitive_clustering() -> bool:
    """A-B accepted, B-C accepted, A-C never directly compared (different
    marks, so Phase 12.2 never even generates that pair) -- must still
    merge into ONE three-observation identity via connected components."""
    from core.fusion.observation_builder import NAMESPACE_FACT
    from core.fusion.models import (
        ASPECT_MARK, ASPECT_SHAPE, DrawingRole, ObservationFact, PhysicalObservation,
    )
    from core.fusion.hypothesis_generator import generate_hypotheses
    from core.fusion.evidence_engine import score_hypotheses
    from core.fusion.identity_resolver import resolve_identities

    def _fact(obs_uuid, aspect, value):
        return ObservationFact(
            uuid=uuid.uuid5(NAMESPACE_FACT, f"{obs_uuid}|{aspect}"),
            aspect=aspect, value=value, confidence=1.0, source="synthetic",
        )

    role = DrawingRole(role="unclassified", confidence=1.0, evidence="synthetic fixture")
    a_uuid, b_uuid, c_uuid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    # A and B share mark "N9" (accepted pair). B and C share mark "N9-ALT"
    # -- to let B bridge both without A and C ever sharing a mark, B
    # carries facts under BOTH of its own aspect claims via two
    # observations is not directly expressible with one mark field, so
    # instead: A<->B share mark N9; B<->C share a distinct qualifying
    # fact_agreement (shape) with no conflicting facts at all, keeping
    # both pairs unanimous (every scored category == 1.0) without A and C
    # ever being evaluated against each other (different drawing_number
    # would fully isolate them; instead we rely on A-C simply not
    # appearing in any hypothesis's candidate list, since observations
    # only pair with the same-mark or fact-agreeing ones).
    a = PhysicalObservation(
        uuid=a_uuid, drawing_filename="a.dxf", drawing_number="TEST-ELEMENT", drawing_view="M1",
        drawing_role=role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[_fact(a_uuid, ASPECT_MARK, "N9")],
    )
    b = PhysicalObservation(
        uuid=b_uuid, drawing_filename="b.dxf", drawing_number="TEST-ELEMENT", drawing_view="M2",
        drawing_role=role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[_fact(b_uuid, ASPECT_MARK, "N9"), _fact(b_uuid, ASPECT_SHAPE, "branch")],
    )
    c = PhysicalObservation(
        uuid=c_uuid, drawing_filename="c.dxf", drawing_number="TEST-ELEMENT", drawing_view="SCHEDULE",
        drawing_role=role, family_uuid=uuid.uuid4(), mark_namespace="reference_code",
        family_type="main_bar", bbox=(0, 0, 0, 0),
        facts=[_fact(c_uuid, ASPECT_SHAPE, "branch")],
    )

    hyps = generate_hypotheses([a, b, c])
    scored = score_hypotheses(hyps, [a, b, c])
    decisions, identities = resolve_identities(scored, [a, b, c])

    ab = next((d for d in decisions if {d.anchor_observation, d.candidate_observation} == {a_uuid, b_uuid}), None)
    bc = next((d for d in decisions if {d.anchor_observation, d.candidate_observation} == {b_uuid, c_uuid}), None)
    ac_exists = any({d.anchor_observation, d.candidate_observation} == {a_uuid, c_uuid} for d in decisions)

    ok = (
        ab is not None and ab.outcome == "ACCEPTED"
        and bc is not None and bc.outcome == "ACCEPTED"
        and not ac_exists
        and len(identities) == 1
        and set(identities[0].observations) == {a_uuid, b_uuid, c_uuid}
    )
    print(f"[transitive] A-B={ab.outcome if ab else None}, B-C={bc.outcome if bc else None}, "
          f"A-C ever compared={ac_exists}, identities={len(identities)} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_no_geometry_import() -> bool:
    """Boundary guardrail: this subphase must not IMPORT core.reconstruction
    (mentioning it in a docstring, to explain the boundary, is fine)."""
    import ast

    path = os.path.join(os.path.dirname(__file__), "..", "core", "fusion", "identity_resolver.py")
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    ok = not any(m.startswith("core.reconstruction") for m in imported_modules)
    print(f"[boundary] identity_resolver.py's actual imports: {imported_modules} -> {'OK' if ok else 'LEAKED'}")
    return ok


def run_check(directory: str) -> int:
    results = [
        check_determinism(directory),
        check_real_data_regression(directory),
        check_decision_preservation(directory),
        check_synthetic_accepted(),
        check_transitive_clustering(),
        check_no_geometry_import(),
    ]
    if all(results):
        print("\nPHASE 12.4 CHECKS PASSED ✅")
        return 0
    print("\nPHASE 12.4 CHECKS FAILED ❌")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_phase12_identity_resolver.py <directory>")
        sys.exit(1)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    sys.exit(run_check(sys.argv[1]))
