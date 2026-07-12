"""
core/fusion/hypothesis_generator.py — Phase 12.2: Hypothesis Generator.

For every observation, asks "who could I be?" -- never "who am I?". Builds
one IdentityHypothesis per observation (the anchor), listing every OTHER
observation that has at least one qualifying, non-spatial reason to be
considered a candidate, plus the full evidence trail (including negative
evidence, e.g. fact conflicts) for every pair actually considered.

Implementation objective (as specified before this subphase started):
build a deterministic, exhaustive hypothesis generator that produces
candidate identity groups from observations, but makes no decisions. No
scoring. No acceptance. No merging. No geometry. Every IdentityHypothesis
this module produces has status=PENDING; nothing here ever sets ACCEPTED
or REJECTED (that's Phase 12.3, the Evidence Engine).

Candidate generation ordering (research report Addendum 3):
  1. Same drawing_number (Phase 1's existing grouping) -- a hard scope
     boundary, not a selectivity heuristic: marks are not globally
     unique across elements, so this prevents a false cross-element
     merge before any other reasoning happens.
  2. Same mark, namespace-aware (never compare a self_decoding mark
     against a reference_code mark as the same kind of thing).
  3. Compatible drawing_role (mould_instance <-> reinforcement_typical
     is a genuinely complementary pair; corroborating, not a qualifier
     on its own).
  4. Fact agreement/conflict on any aspect both observations claim --
     agreement can qualify a pair on its own even without a mark match;
     conflict is recorded as evidence, never used to exclude a pair here.
  5. Spatial distance -- always attached as evidence when both
     observations have a POSITION fact, but never sufficient on its own
     to qualify a pair. This is deliberate: admitting a pair on spatial
     proximity alone would make spatial the de facto primary filter,
     exactly what Addendum 1/3 argue against for cross-view-type pairs
     that often share no coordinate frame at all.

"Candidate generation must be complete before it is selective" (research
report Addendum 3): every pair that qualifies is kept, including pairs
with conflicting facts -- Phase 12.3 needs the conflict on record to
explain a later rejection, not a generator that silently dropped it.
"""
from __future__ import annotations

import math
import uuid
from typing import Dict, List

from core.fusion.models import (
    ASPECT_MARK, ASPECT_POSITION,
    EVIDENCE_CATEGORY_ENGINEERING_CONTEXT, EVIDENCE_CATEGORY_FACT,
    EVIDENCE_CATEGORY_ROLE, EVIDENCE_CATEGORY_SPATIAL,
    POLARITY_CONTRADICTS, POLARITY_SUPPORTS, POLARITY_UNKNOWN,
    Evidence, IdentityHypothesis, PhysicalObservation,
)

# Fixed namespace so an IdentityHypothesis's UUID is a pure function of its
# anchor observation -- same determinism discipline as every other phase.
NAMESPACE_HYPOTHESIS = uuid.UUID('f1a8d3c6-2b5e-4a1f-9c7d-3e6b8a2f5d14')
# Fixed namespace for Evidence UUIDs -- a pure function of (observation_a,
# observation_b, rule), so an evidence item's identity is stable across runs.
NAMESPACE_EVIDENCE = uuid.UUID('a3d6e9b2-7f4c-4d8a-9e1b-6c2f5a8d3b71')

_COMPLEMENTARY_ROLES = {frozenset({"mould_instance", "reinforcement_typical"})}


def _evidence(rule, category, polarity, description, obs_a, obs_b) -> Evidence:
    # category/polarity are categorical labels, not scores -- confidence
    # stays None here; Phase 12.3 is the only place that gets filled in.
    return Evidence(
        uuid=uuid.uuid5(NAMESPACE_EVIDENCE, f"{obs_a}|{obs_b}|{rule}"),
        category=category, polarity=polarity, rule=rule, description=description,
        observation_a=obs_a, observation_b=obs_b,
    )


def _pair_evidence(a: PhysicalObservation, b: PhysicalObservation) -> List[Evidence]:
    evidence: List[Evidence] = []

    mark_a, mark_b = a.fact(ASPECT_MARK), b.fact(ASPECT_MARK)
    if mark_a and mark_b and mark_a.value == mark_b.value and a.mark_namespace == b.mark_namespace:
        evidence.append(_evidence(
            "same_mark", EVIDENCE_CATEGORY_ENGINEERING_CONTEXT, POLARITY_SUPPORTS,
            f"both observations carry mark '{mark_a.value}' in the '{a.mark_namespace}' namespace",
            a.uuid, b.uuid,
        ))

    if a.drawing_role.role != b.drawing_role.role:
        if frozenset({a.drawing_role.role, b.drawing_role.role}) in _COMPLEMENTARY_ROLES:
            evidence.append(_evidence(
                "complementary_role", EVIDENCE_CATEGORY_ROLE, POLARITY_SUPPORTS,
                f"'{a.drawing_role.role}' and '{b.drawing_role.role}' are a confirmed "
                f"complementary view pair (research report Step 1)",
                a.uuid, b.uuid,
            ))

    # MARK is excluded here -- it's already handled above by the dedicated,
    # namespace-aware same_mark check. POSITION is excluded -- handled below
    # by spatial_distance, which is never a qualifying signal on its own.
    shared_aspects = {f.aspect for f in a.facts} & {f.aspect for f in b.facts} - {ASPECT_POSITION, ASPECT_MARK}
    for aspect in sorted(shared_aspects):
        fa, fb = a.fact(aspect), b.fact(aspect)
        if fa.value == fb.value:
            evidence.append(_evidence(
                "fact_agreement", EVIDENCE_CATEGORY_FACT, POLARITY_SUPPORTS,
                f"both observations claim {aspect}={fa.value}", a.uuid, b.uuid,
            ))
        else:
            evidence.append(_evidence(
                "fact_conflict", EVIDENCE_CATEGORY_FACT, POLARITY_CONTRADICTS,
                f"observations disagree on {aspect}: {fa.value} vs {fb.value}", a.uuid, b.uuid,
            ))

    pos_a, pos_b = a.fact(ASPECT_POSITION), b.fact(ASPECT_POSITION)
    if pos_a and pos_b:
        (xa, ya), (xb, yb) = pos_a.value, pos_b.value
        distance = math.hypot(xa - xb, ya - yb)
        # UNKNOWN, not supports/contradicts: no calibrated distance
        # threshold exists yet (only one real drawing's worth of data),
        # and inventing one would be exactly the hardcoded-threshold
        # shortcut this project has avoided everywhere else. See
        # docs/audits/phase12/12.3_evidence_engine.md.
        evidence.append(_evidence(
            "spatial_distance", EVIDENCE_CATEGORY_SPATIAL, POLARITY_UNKNOWN,
            f"centroid distance {distance:.1f}mm (corroborating only, "
            f"never a qualifying signal on its own)", a.uuid, b.uuid,
        ))

    return evidence


def _qualifies(evidence: List[Evidence]) -> bool:
    """A pair is 'plausible' enough to include in a hypothesis if it has
    at least one non-spatial rule firing -- same_mark or fact_agreement.
    complementary_role and fact_conflict alone don't qualify a pair
    (too weak/negative on their own); spatial_distance never qualifies a
    pair on its own, by design (see module docstring)."""
    return any(e.rule in ("same_mark", "fact_agreement") for e in evidence)


def generate_hypotheses(observations: List[PhysicalObservation]) -> List[IdentityHypothesis]:
    """One IdentityHypothesis per observation (as anchor). Deterministic:
    grouped by drawing_number, pairs evaluated in a fixed sorted order,
    output sorted by anchor observation UUID."""
    by_drawing_number: Dict[str, List[PhysicalObservation]] = {}
    for obs in observations:
        by_drawing_number.setdefault(obs.drawing_number, []).append(obs)
    for group in by_drawing_number.values():
        group.sort(key=lambda o: str(o.uuid))

    hypotheses: List[IdentityHypothesis] = []
    for group in by_drawing_number.values():
        for anchor in group:
            candidates: List = []
            all_evidence: List[Evidence] = []
            for other in group:
                if other.uuid == anchor.uuid:
                    continue
                pair_evidence = _pair_evidence(anchor, other)
                if not pair_evidence:
                    continue  # nothing shared at all -- not "considered," never recorded
                # Every pair with SOME evidence is recorded, whether or not
                # it qualifies as a candidate -- this is what lets a later
                # viewer/audit answer "considered and rejected" (evidence
                # present, not in candidate_observations) distinctly from
                # "never considered" (no evidence entry at all).
                all_evidence.extend(pair_evidence)
                if _qualifies(pair_evidence):
                    candidates.append(other.uuid)

            hypotheses.append(IdentityHypothesis(
                uuid=uuid.uuid5(NAMESPACE_HYPOTHESIS, str(anchor.uuid)),
                anchor_observation=anchor.uuid,
                candidate_observations=sorted(candidates, key=str),
                evidence=all_evidence,
            ))

    hypotheses.sort(key=lambda h: str(h.anchor_observation))
    return hypotheses
