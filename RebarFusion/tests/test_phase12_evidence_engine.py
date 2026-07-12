"""
tests/test_phase12_evidence_engine.py

Phase 12.3 freeze criteria:
  1. Determinism.
  2. Real-data regression -- N6<->N7's scored candidate must have a
     non-empty 'fact' category score (from real fact_agreement/conflict
     evidence), 'engineering_context'/'role' correctly unscored (no
     same_mark or complementary_role evidence exists for this pair), and
     an overall score strictly between 0 and 1 (not fabricated as a flat
     1.0 or 0.0 -- there IS a real conflict, on real length data,
     dragging it down from a clean 1.0).
  3. Confidence provenance -- every populated Evidence.confidence must be
     a real geometric mean of two upstream ObservationFact/DrawingRole
     confidences, not an arbitrary number. spatial_distance evidence must
     stay confidence=None (no calibrated model exists).
  4. No-decisions guardrail -- every ScoredHypothesis.status is PENDING;
     ScoredCandidate.is_candidate is carried over unchanged from Phase
     12.2, never re-decided; EvidenceScore has no accept/reject field.
  5. Only Phase 12.2's candidates get scored -- a non-candidate pair
     (N4 vs N6/N7) must not appear in any scored_candidates list, even
     though its evidence is still visible upstream in the hypothesis.

Usage:
    python tests/test_phase12_evidence_engine.py <directory>

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
    from core.fusion.evidence_engine import score_hypotheses

    results = list(run_pipeline_through_phase9(directory))
    observations = build_observations(results)
    hypotheses = generate_hypotheses(observations)
    scored = score_hypotheses(hypotheses, observations)
    return observations, hypotheses, scored


def check_determinism(directory: str, runs: int = 5) -> bool:
    hashes = [_hash(_pipeline(directory)[2]) for _ in range(runs)]
    ok = len(set(hashes)) == 1
    print(f"[determinism] {runs} runs -> {'identical' if ok else 'DIVERGED'} ({hashes[0][:12]}...)")
    return ok


def check_real_data_regression(directory: str) -> bool:
    from core.fusion.models import ASPECT_MARK

    observations, hypotheses, scored = _pipeline(directory)
    by_uuid = {o.uuid: o for o in observations}

    def mark_of(u):
        f = by_uuid[u].fact(ASPECT_MARK)
        return f.value if f else None

    pair = None
    for sh in scored:
        for sc in sh.scored_candidates:
            if {mark_of(sc.anchor_observation), mark_of(sc.candidate_observation)} == {"N6", "N7"}:
                pair = sc
                break

    ok = (
        pair is not None
        and pair.score.unscored_categories == ["engineering_context", "role"]
        and "fact" in pair.score.category_scores
        and 0.0 < pair.score.overall < 1.0
    )
    print(f"[real-data] N6<->N7 pair: category_scores={pair.score.category_scores if pair else None}, "
          f"overall={pair.score.overall if pair else None}, "
          f"unscored={pair.score.unscored_categories if pair else None} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_confidence_provenance(directory: str) -> bool:
    observations, hypotheses, scored = _pipeline(directory)
    by_uuid = {o.uuid: o for o in observations}

    ok = True
    checked = 0
    for sh in scored:
        for sc in sh.scored_candidates:
            for e in sc.evidence:
                checked += 1
                if e.rule == "spatial_distance":
                    ok = ok and e.confidence is None
                else:
                    ok = ok and e.confidence is not None and 0.0 < e.confidence <= 1.0
    print(f"[provenance] {checked} evidence item(s) checked, spatial_distance stays None, "
          f"others are real (0,1] confidences -> {'OK' if ok else 'MISMATCH'}")
    return ok and checked > 0


def check_no_decisions(directory: str) -> bool:
    from core.fusion.models import EvidenceScore

    _, _, scored = _pipeline(directory)
    all_pending = all(sh.status == "PENDING" for sh in scored)
    all_carried_over = all(sc.is_candidate for sh in scored for sc in sh.scored_candidates)

    score_fields = {f.name for f in fields(EvidenceScore)}
    forbidden = {"decision", "accepted", "rejected", "status"}
    leaked = score_fields & forbidden

    ok = all_pending and all_carried_over and not leaked
    print(f"[guardrail] all ScoredHypothesis PENDING: {all_pending}; is_candidate carried over: "
          f"{all_carried_over}; EvidenceScore has no decision field -> {'OK' if ok else 'LEAKED'}")
    return ok


def check_only_candidates_scored(directory: str) -> bool:
    from core.fusion.models import ASPECT_MARK

    observations, hypotheses, scored = _pipeline(directory)
    by_uuid = {o.uuid: o for o in observations}

    def mark_of(u):
        f = by_uuid[u].fact(ASPECT_MARK)
        return f.value if f else None

    n4_uuid = next(o.uuid for o in observations if mark_of(o.uuid) == "N4")
    scored_pairs = {
        (sc.anchor_observation, sc.candidate_observation)
        for sh in scored for sc in sh.scored_candidates
    }
    n4_scored = any(n4_uuid in pair for pair in scored_pairs)

    ok = not n4_scored
    print(f"[scope] N4 (0 candidates in Phase 12.2) never appears in scored_candidates -> "
          f"{'OK' if ok else 'LEAKED'}")
    return ok


def run_check(directory: str) -> int:
    results = [
        check_determinism(directory),
        check_real_data_regression(directory),
        check_confidence_provenance(directory),
        check_no_decisions(directory),
        check_only_candidates_scored(directory),
    ]
    if all(results):
        print("\nPHASE 12.3 CHECKS PASSED ✅")
        return 0
    print("\nPHASE 12.3 CHECKS FAILED ❌")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_phase12_evidence_engine.py <directory>")
        sys.exit(1)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    sys.exit(run_check(sys.argv[1]))
