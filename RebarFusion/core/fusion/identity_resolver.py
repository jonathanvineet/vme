"""
core/fusion/identity_resolver.py — Phase 12.4: Identity Resolver.

Reads Phase 12.3's ScoredHypothesis output and makes the one decision
Phase 12.3 explicitly deferred: does a candidate pair become part of the
same physical object? Every decision is recorded as its own
ResolutionDecision -- rationale preserved for ACCEPTED, REJECTED, and
REVIEW alike -- before any PhysicalIdentity is built. The identity only
ever represents the accepted result; the decision explains how the
system got there, and is never discarded just because it wasn't ACCEPTED.

Boundary (as specified before this subphase started): Phase 12.4 may
create PhysicalIdentity objects. It may not reconstruct geometry or
modify the reconstruction engine. Phase 10 still owns HOW a bar is
built; this subphase only decides WHICH observations belong to the same
one. Nothing here imports from core.reconstruction.

Decision rule (v1 -- deliberately not a single tuned float threshold):
for a candidate pair's EvidenceScore,
  - every scored category == 1.0 (no contradicting evidence anywhere)  -> ACCEPTED
  - any scored category == 0.0 (a category that's pure contradiction)  -> REJECTED
  - otherwise (some support, some contradiction, nothing unanimous)     -> REVIEW
This is a boolean rule over category_scores' shape, not a tuned cutoff
on `overall` -- there is exactly one real candidate pair (N6<->N7) to
calibrate against today, and picking a specific float (e.g. 0.7) against
n=1 would be exactly the unjustified-threshold shortcut this project has
avoided everywhere else. N6<->N7 lands in REVIEW under this rule: a real
conflict on real data (their length disagrees), not a manufactured pass.
Revisit once more real cross-drawing data exists to calibrate against
(see docs/audits/phase12/12.4_identity_resolver.md).
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Set, Tuple

from core.fusion.models import (
    HYPOTHESIS_ACCEPTED, HYPOTHESIS_REJECTED, HYPOTHESIS_REVIEW,
    Claim, PhysicalIdentity, ResolutionDecision, ScoredHypothesis,
)

NAMESPACE_DECISION = uuid.UUID('b7e4c2a9-1f6d-4b3e-8a5c-9d2f7e1b4c86')
NAMESPACE_IDENTITY = uuid.UUID('d5a1f8c3-6b2e-4d9a-8f4c-3e7b1a6d2f95')
NAMESPACE_CLAIM = uuid.UUID('9c3f6a2e-4b8d-4e1c-9a7f-2d5b8c4e6a13')


def _decide(score) -> str:
    if not score.category_scores:
        return HYPOTHESIS_REJECTED
    values = list(score.category_scores.values())
    if all(v == 1.0 for v in values):
        return HYPOTHESIS_ACCEPTED
    if any(v == 0.0 for v in values):
        return HYPOTHESIS_REJECTED
    return HYPOTHESIS_REVIEW


def _build_decisions(scored_hypotheses: List[ScoredHypothesis]) -> List[ResolutionDecision]:
    """One decision per unordered observation pair, not per (anchor,
    candidate) direction -- generate_hypotheses (12.2) produces both N6's
    hypothesis (candidate N7) and N7's hypothesis (candidate N6) for the
    same real pair; deduping here avoids two contradictory-looking
    'separate' decisions about the same physical question."""
    seen: Set[frozenset] = set()
    decisions: List[ResolutionDecision] = []
    for sh in scored_hypotheses:
        for sc in sh.scored_candidates:
            pair = frozenset({sc.anchor_observation, sc.candidate_observation})
            if pair in seen:
                continue
            seen.add(pair)
            outcome = _decide(sc.score)
            decisions.append(ResolutionDecision(
                uuid=uuid.uuid5(NAMESPACE_DECISION, "|".join(sorted(str(x) for x in pair))),
                hypothesis_uuid=sh.uuid,
                anchor_observation=sc.anchor_observation,
                candidate_observation=sc.candidate_observation,
                outcome=outcome,
                rationale=list(sc.evidence),
                overall_confidence=sc.score.overall,
                promoted=outcome == HYPOTHESIS_ACCEPTED,
            ))
    decisions.sort(key=lambda d: str(d.uuid))
    return decisions


def _connected_components(accepted_pairs: List[Tuple]) -> List[Set]:
    """Union-find over ACCEPTED pairs: an observation accepted into two
    different pairs joins one identity, not two separate ones."""
    parent: Dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in accepted_pairs:
        union(a, b)

    groups: Dict = {}
    for node in parent:
        groups.setdefault(find(node), set()).add(node)
    return list(groups.values())


def resolve_identities(
    scored_hypotheses: List[ScoredHypothesis], observations
) -> Tuple[List[ResolutionDecision], List[PhysicalIdentity]]:
    """Returns (all decisions, resolved identities). Decisions cover every
    scored candidate pair regardless of outcome. Identities are built only
    from ACCEPTED pairs; each identity's `provenance` also lists every
    REJECTED/REVIEW decision touching any of its member observations, so
    'why wasn't X included' stays answerable from the identity itself."""
    by_uuid = {o.uuid: o for o in observations}
    decisions = _build_decisions(scored_hypotheses)

    accepted_pairs = [
        (d.anchor_observation, d.candidate_observation)
        for d in decisions if d.outcome == HYPOTHESIS_ACCEPTED
    ]
    components = _connected_components(accepted_pairs)

    identities: List[PhysicalIdentity] = []
    for component in components:
        obs_uuids = sorted(component, key=str)
        obs_set = set(obs_uuids)
        identity_uuid = uuid.uuid5(NAMESPACE_IDENTITY, "|".join(str(u) for u in obs_uuids))

        member_decisions = [
            d for d in decisions
            if d.outcome == HYPOTHESIS_ACCEPTED
            and {d.anchor_observation, d.candidate_observation} <= obs_set
        ]

        claims = [
            Claim(
                uuid=uuid.uuid5(NAMESPACE_CLAIM, f"{identity_uuid}|{obs_uuid}"),
                observation_uuid=obs_uuid,
                identity_uuid=identity_uuid,
                facts=list(by_uuid[obs_uuid].facts),
                claim_confidence=next(
                    (d.overall_confidence for d in member_decisions
                     if obs_uuid in (d.anchor_observation, d.candidate_observation)),
                    0.0,
                ),
            )
            for obs_uuid in obs_uuids
        ]

        primary_decision = min(member_decisions, key=lambda d: str(d.uuid))
        provenance = sorted(
            {d.uuid for d in decisions
             if {d.anchor_observation, d.candidate_observation} & obs_set},
            key=str,
        )

        identities.append(PhysicalIdentity(
            uuid=identity_uuid, claims=claims, observations=obs_uuids,
            decision_uuid=primary_decision.uuid, provenance=provenance,
        ))

    identities.sort(key=lambda i: str(i.uuid))
    return decisions, identities
